# rag_setup.py
import os
import json
import threading
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

load_dotenv(override=True)

TIMESTAMP_FILE = "rag_timestamp.json"
FAISS_INDEX_DIR = "faiss_index"
FAISS_INDEX_NAME = "knowledge_base"


class RAGManager:
    """線程安全的 RAG 向量儲存管理器"""
    
    def __init__(self):
        self._vector_store: Optional[FAISS] = None
        self._lock = threading.RLock()  # 使用可重入鎖
        self._is_loading = False
        self._load_event = threading.Event()
        
    @property
    def vector_store(self) -> Optional[FAISS]:
        """安全地獲取向量儲存實例"""
        with self._lock:
            return self._vector_store
            
    def _set_vector_store(self, store: Optional[FAISS]) -> None:
        """安全地設置向量儲存實例"""
        with self._lock:
            self._vector_store = store
            
    def is_ready(self) -> bool:
        """檢查 RAG 系統是否已準備就緒"""
        with self._lock:
            return self._vector_store is not None
            
    def wait_for_ready(self, timeout: float = 30.0) -> bool:
        """等待 RAG 系統準備就緒，帶超時機制"""
        if self.is_ready():
            return True
            
        # 如果正在載入，等待載入完成
        if self._is_loading:
            return self._load_event.wait(timeout)
            
        return False
        
    def search_knowledge_base(self, query: str, k: int = 3) -> str:
        """線程安全的知識庫搜尋"""
        # 等待系統準備就緒
        if not self.wait_for_ready():
            return "知識庫尚未準備就緒，請稍後再試。"
            
        with self._lock:
            if not self._vector_store:
                return "知識庫尚未初始化。"
                
            try:
                retriever = self._vector_store.as_retriever(search_kwargs={"k": k})
                relevant_docs = retriever.invoke(query)
                
                context = "\n\n---\n\n".join(
                    [
                        f"來源: {doc.metadata.get('Header 2', '')} > {doc.metadata.get('Header 3', '')}\n內容: {doc.page_content}"
                        for doc in relevant_docs
                    ]
                )
                return f"從知識庫中找到的相關資訊如下：\n{context}"
            except Exception as e:
                print(f"搜尋知識庫時發生錯誤: {e}")
                return f"搜尋知識庫時發生錯誤: {str(e)}"


# 全域 RAG 管理器實例
rag_manager = RAGManager()


def get_file_mtime(file_path):
    """獲取文件的修改時間"""
    if os.path.exists(file_path):
        return os.path.getmtime(file_path)
    return 0


def load_timestamp():
    """載入上次 embedding 的時間戳記"""
    if os.path.exists(TIMESTAMP_FILE):
        try:
            with open(TIMESTAMP_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("last_embedding_time", 0)
        except:
            return 0
    return 0


def save_timestamp():
    """保存當前時間戳記"""
    with open(TIMESTAMP_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_embedding_time": datetime.now().timestamp()}, f)


def save_local():
    """將 FAISS 向量儲存保存到本地"""
    global rag_manager
    current_store = rag_manager.vector_store
    if not current_store:
        print("❌ 無法保存：向量儲存尚未初始化")
        return False
    
    try:
        os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
        current_store.save_local(FAISS_INDEX_DIR, FAISS_INDEX_NAME)
        save_timestamp()
        print(f"FAISS 向量儲存已保存至 {FAISS_INDEX_DIR}/{FAISS_INDEX_NAME}")
        return True
    except Exception as e:
        print(f"保存 FAISS 向量儲存時發生錯誤: {e}")
        return False


def load_local():
    """從本地載入 FAISS 向量儲存"""
    global rag_manager
    
    faiss_path = os.path.join(FAISS_INDEX_DIR, f"{FAISS_INDEX_NAME}.faiss")
    pkl_path = os.path.join(FAISS_INDEX_DIR, f"{FAISS_INDEX_NAME}.pkl")
    
    if not (os.path.exists(faiss_path) and os.path.exists(pkl_path)):
        print(f"找不到現有的 FAISS 索引檔案")
        return False
    
    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        loaded_store = FAISS.load_local(
            FAISS_INDEX_DIR, 
            embeddings, 
            FAISS_INDEX_NAME,
            allow_dangerous_deserialization=True
        )
        rag_manager._set_vector_store(loaded_store)
        print(f"已成功載入 FAISS 向量儲存")
        return True
    except Exception as e:
        print(f"載入 FAISS 向量儲存時發生錯誤: {e}")
        rag_manager._set_vector_store(None)
        return False


def needs_re_embedding(markdown_path):
    """檢查是否需要重新 embedding"""
    if not rag_manager.vector_store:
        return True
    
    file_mtime = get_file_mtime(markdown_path)
    last_embedding_time = load_timestamp()
    
    return file_mtime > last_embedding_time


def setup_rag():
    """設置 RAG 系統，使用線程安全的管理器"""
    global rag_manager
    
    with rag_manager._lock:
        # 設置載入狀態
        rag_manager._is_loading = True
        rag_manager._load_event.clear()
        
        try:
            # 知識庫文件路徑 - 從環境變數讀取，預設為相對路徑
            markdown_path = os.getenv("KNOWLEDGE_BASE_PATH", "docs/Museum_Collection_Info.md")

            if not os.path.exists(markdown_path):
                print(f"錯誤：找不到知識庫文件 {markdown_path}")
                print(f"請確保檔案路徑正確，或設置 KNOWLEDGE_BASE_PATH 環境變數")
                rag_manager._set_vector_store(None)
                return
            
            # 首先嘗試載入現有的 FAISS 索引
            if load_local():
                # 檢查載入的向量儲存是否需要更新
                if not needs_re_embedding(markdown_path):
                    print("已載入現有向量儲存，知識庫文件未更新")
                    return
                else:
                    print("知識庫文件已更新，需要重新建立向量儲存")
            else:
                print("未找到現有向量儲存，將建立新的索引")

            try:
                with open(markdown_path, "r", encoding="utf-8") as f:
                    markdown_document = f.read()

                if not markdown_document.strip():
                    print(f"警告：知識庫文件 {markdown_path} 是空的")
                    rag_manager._set_vector_store(None)
                    return

                # 1. 定義要根據哪些 Markdown 標題進行分割
                headers_to_split_on = [
                    ("#", "Header 1"),
                    ("##", "Header 2"),
                    ("###", "Header 3"),
                ]

                # 2. 實例化 Markdown 分割器
                markdown_splitter = MarkdownHeaderTextSplitter(
                    headers_to_split_on=headers_to_split_on
                )
                md_header_splits = markdown_splitter.split_text(markdown_document)

                if not md_header_splits:
                    print(f"警告：無法從 {markdown_path} 中提取到任何文檔片段")
                    rag_manager._set_vector_store(None)
                    return

                # 3. 建立 embeddings 和向量儲存
                # LangChain 的 FAISS.from_documents 會自動處理 Document 物件
                print("正在重新建立向量儲存...")
                embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
                new_vector_store = FAISS.from_documents(md_header_splits, embeddings)
                
                # 安全地設置新的向量儲存
                rag_manager._set_vector_store(new_vector_store)
                
                # 保存向量儲存到本地
                if save_local():
                    print("RAG 系統已成功初始化並保存 (使用 Markdown 分割)！")
                else:
                    print("RAG 系統已初始化，但保存失敗")
                
            except FileNotFoundError:
                print(f"錯誤：無法讀取知識庫文件 {markdown_path}")
                rag_manager._set_vector_store(None)
            except UnicodeDecodeError:
                print(f"錯誤：知識庫文件 {markdown_path} 編碼格式不正確")
                rag_manager._set_vector_store(None)
            except Exception as e:
                print(f"錯誤：初始化 RAG 系統時發生未預期的錯誤: {e}")
                rag_manager._set_vector_store(None)
                
        finally:
            # 完成載入，通知等待的線程
            rag_manager._is_loading = False
            rag_manager._load_event.set()


# 使用 RAGManager 的搜尋函數（向後相容）
def search_knowledge_base(query: str) -> str:
    """向後相容的搜尋函數，使用線程安全的 RAGManager"""
    global rag_manager
    return rag_manager.search_knowledge_base(query)
