# tools.py
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
    print(f"Executing web search for: {query}")
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]

            if not results:
                return "在網路上找不到相關資訊。"

            formatted_results = []
            for i, result in enumerate(results, 1):
                title = result.get("title", "無標題")
                body = result.get("body", "無內容摘要")
                href = result.get("href", "")

                formatted_result = f"""### 搜尋結果 {i}: {title}
**來源**: {href}
**摘要**: {body}
---"""
                formatted_results.append(formatted_result)

            return "\n\n".join(formatted_results)

    except Exception as e:
        return f"網路搜尋時發生錯誤: {str(e)}"


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
