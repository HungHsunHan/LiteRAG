# tools.py
import re
import time
from duckduckgo_search import DDGS

from rag_setup import search_knowledge_base


# 1. RAG 工具
def local_rag_search(query: str):
    """
    查詢本地知識庫中的資訊。適用於：
    - 博物館收藏品相關問題
    - 歷史文物資訊
    - 已存儲的專業知識
    - 內部文檔內容
    
    回傳格式會標明「從知識庫中找到的相關資訊」。
    """
    print(f"Executing RAG search for: {query}")
    return search_knowledge_base(query)


# 2. 網路搜尋工具
def clean_search_query(query: str) -> str:
    """
    清理和優化搜索關鍵詞，移除可能影響搜索效果的內容
    """
    # 移除常見的對話相關詞彙，專注於實際搜索內容
    cleaned = query.strip()
    
    # 移除可能來自對話上下文的無關詞彙
    context_words = [
        "博物館", "收藏品", "文物", "知識庫", "本地", "資料庫",
        "請問", "你好", "幫我", "查詢", "搜尋", "找", "告訴我"
    ]
    
    # 如果查詢包含時事相關詞彙，優先保留
    news_keywords = ["新聞", "最新", "今日", "今天", "現在", "目前", "即時", "時事", "最近"]
    if any(keyword in cleaned for keyword in news_keywords):
        # 移除上下文詞彙但保留新聞相關內容
        for word in context_words:
            cleaned = re.sub(rf'\b{word}\b', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # 限制查詢長度，避免過於複雜的搜索
    if len(cleaned) > 50:
        cleaned = cleaned[:50].rsplit(' ', 1)[0]  # 在最後一個空格處截斷
    
    return cleaned if cleaned else query  # 如果清理後為空，返回原查詢


def web_search(query: str):
    """
    搜尋網路上的最新即時資訊。適用於：
    - 時事新聞和當前事件
    - 股價、匯率等即時數據
    - 天氣資訊
    - 最新科技發展
    - 本地知識庫未涵蓋的主題
    
    回傳格式包含標題、來源連結和內容摘要，標明「搜尋結果」。
    """
    original_query = query
    cleaned_query = clean_search_query(query)
    
    print(f"=== WEB SEARCH DEBUG ===")
    print(f"原始查詢: {original_query}")
    print(f"清理後查詢: {cleaned_query}")
    print(f"查詢長度: {len(cleaned_query)}")
    
    # 重試機制：嘗試不同的搜索策略
    search_attempts = [
        {"query": cleaned_query, "max_results": 5},  # 增加結果數量
        {"query": original_query, "max_results": 3},  # 嘗試原始查詢
        {"query": cleaned_query.split()[-3:], "max_results": 3} if len(cleaned_query.split()) > 3 else None  # 最後3個關鍵詞
    ]
    
    # 過濾掉 None 項目
    search_attempts = [attempt for attempt in search_attempts if attempt is not None]
    
    for attempt_num, attempt in enumerate(search_attempts, 1):
        try:
            query_to_use = " ".join(attempt["query"]) if isinstance(attempt["query"], list) else attempt["query"]
            max_results = attempt["max_results"]
            
            print(f"嘗試 {attempt_num}: 搜索 '{query_to_use}' (最大結果: {max_results})")
            
            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query_to_use, max_results=max_results):
                    results.append(r)
                
                print(f"搜索返回 {len(results)} 個結果")
                
                if results:
                    formatted_results = []
                    for i, result in enumerate(results[:3], 1):  # 最多顯示3個結果
                        title = result.get("title", "無標題")
                        body = result.get("body", "無內容摘要")
                        href = result.get("href", "")
                        
                        print(f"結果 {i}: {title[:50]}...")
                        
                        formatted_result = f"""### 搜尋結果 {i}: {title}
**來源**: {href}
**摘要**: {body}
---"""
                        formatted_results.append(formatted_result)
                    
                    final_result = "\n\n".join(formatted_results)
                    print(f"=== 搜索成功，返回 {len(formatted_results)} 個格式化結果 ===")
                    return final_result
                
        except Exception as e:
            print(f"嘗試 {attempt_num} 失敗: {str(e)}")
            if attempt_num < len(search_attempts):
                print(f"等待 1 秒後重試...")
                time.sleep(1)
            continue
    
    # 所有嘗試都失敗
    error_msg = f"網路搜尋失敗。\n原始查詢: {original_query}\n清理後查詢: {cleaned_query}\n已嘗試 {len(search_attempts)} 種搜索策略，均未找到結果。"
    print(f"=== {error_msg} ===")
    return error_msg


# 這是要傳遞給 OpenAI API 的工具列表
# 格式必須符合 OpenAI 的要求
available_tools = {
    "local_rag_search": local_rag_search,
    "web_search": web_search,
}

tools_specs = [
    {
        "type": "function",
        "function": {
            "name": "local_rag_search",
            "description": "查詢本地知識庫中的專業資訊，包括博物館收藏品、歷史文物、內部文檔等已存儲的知識內容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜尋的具體問題或關鍵字，例如：'秦朝竹簡'、'玉器文化'、'博物館展品介紹'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search", 
            "description": "搜尋網路上的最新即時資訊，包括時事新聞、股價匯率、天氣資訊、最新科技發展等本地知識庫未涵蓋的內容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜尋的具體問題或關鍵字，例如：'今日台股指數'、'最新COVID疫情'、'OpenAI最新消息'、'台北天氣預報'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
