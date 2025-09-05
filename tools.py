# tools.py
from duckduckgo_search import DDGS
from rag_setup import search_knowledge_base


# 1. RAG 工具
def local_rag_search(query: str):
    """
    當需要查詢關於 Gemini AI Assistant 的內部產品資訊或功能時使用此工具。
    """
    print(f"Executing RAG search for: {query}")
    return search_knowledge_base(query)


# 2. 網路搜尋工具
def web_search(query: str):
    """
    當需要查詢最新、即時的資訊，或是本地知識庫沒有涵蓋的主題時使用此工具。
    例如：今天天氣、最新新聞、某家公司的股價等。
    """
    print(f"Executing web search for: {query}")
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
            
            if not results:
                return "在網路上找不到相關資訊。"
            
            formatted_results = []
            for i, result in enumerate(results, 1):
                title = result.get('title', '無標題')
                body = result.get('body', '無內容摘要')
                href = result.get('href', '')
                
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
            "description": "查詢關於 Gemini AI Assistant 的內部產品資訊或功能。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜尋的具體問題或關鍵字",
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
            "description": "查詢最新、即時的資訊，或是本地知識庫沒有涵蓋的主題。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜尋的具體問題或關鍵字，例如 '台北今天天氣' 或 'Nvidia 最新股價'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
