# rag_setup.py
import os
import json
from datetime import datetime

from dotenv import load_dotenv
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

load_dotenv(override=True)

vector_store = None
TIMESTAMP_FILE = "rag_timestamp.json"


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


def needs_re_embedding(markdown_path):
    """檢查是否需要重新 embedding"""
    if not vector_store:
        return True
    
    file_mtime = get_file_mtime(markdown_path)
    last_embedding_time = load_timestamp()
    
    return file_mtime > last_embedding_time


def setup_rag():
    global vector_store

    # 知識庫文件路徑 - 從環境變數讀取，預設為相對路徑
    markdown_path = os.getenv("KNOWLEDGE_BASE_PATH", "docs/Museum_Collection_Info.md")

    if not os.path.exists(markdown_path):
        print(f"錯誤：找不到知識庫文件 {markdown_path}")
        print(f"請確保檔案路徑正確，或設置 KNOWLEDGE_BASE_PATH 環境變數")
        # 創建一個空的向量存儲以避免程式崩潰
        vector_store = None
        return
    
    # 檢查是否需要重新 embedding
    if not needs_re_embedding(markdown_path):
        print("📄 知識庫文件未更新，跳過 embedding 程序")
        return

    try:
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_document = f.read()

        if not markdown_document.strip():
            print(f"警告：知識庫文件 {markdown_path} 是空的")
            vector_store = None
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
            vector_store = None
            return

        # 3. 建立 embeddings 和向量儲存
        # LangChain 的 FAISS.from_documents 會自動處理 Document 物件
        print("🔄 正在重新建立向量儲存...")
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vector_store = FAISS.from_documents(md_header_splits, embeddings)
        
        # 保存時間戳記
        save_timestamp()
        print("✅ RAG 系統已成功初始化 (使用 Markdown 分割)！")
        
    except FileNotFoundError:
        print(f"錯誤：無法讀取知識庫文件 {markdown_path}")
        vector_store = None
    except UnicodeDecodeError:
        print(f"錯誤：知識庫文件 {markdown_path} 編碼格式不正確")
        vector_store = None
    except Exception as e:
        print(f"錯誤：初始化 RAG 系統時發生未預期的錯誤: {e}")
        vector_store = None


# search_knowledge_base 函數保持不變
def search_knowledge_base(query: str) -> str:
    global vector_store
    if not vector_store:
        return "知識庫尚未初始化。"

    retriever = vector_store.as_retriever(search_kwargs={"k": 3})  # 增加檢索數量以應對比較問題
    relevant_docs = retriever.invoke(query)

    context = "\n\n---\n\n".join(
        [
            f"來源: {doc.metadata.get('Header 2', '')} > {doc.metadata.get('Header 3', '')}\n內容: {doc.page_content}"
            for doc in relevant_docs
        ]
    )
    return f"從知識庫中找到的相關資訊如下：\n{context}"
