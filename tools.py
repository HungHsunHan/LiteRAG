# tools.py
from duckduckgo_search import DDGS
from rag_setup import search_knowledge_base


# 1. RAG tool
def local_rag_search(query: str):
    """
    Use this tool when you need to query internal product information or features about Gemini AI Assistant.
    """
    print(f"Executing RAG search for: {query}")
    return search_knowledge_base(query)


# 2. Web search tool
def web_search(query: str):
    """
    Use this tool when you need to query the latest, real-time information, or topics not covered by the local knowledge base.
    For example: today's weather, latest news, stock prices of a company, etc.
    """
    print(f"Executing web search for: {query}")
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
            
            if not results:
                return "No relevant information found on the web."
            
            formatted_results = []
            for i, result in enumerate(results, 1):
                title = result.get('title', 'No title')
                body = result.get('body', 'No content summary')
                href = result.get('href', '')
                
                formatted_result = f"""### Search Result {i}: {title}
**Source**: {href}
**Summary**: {body}
---"""
                formatted_results.append(formatted_result)
            
            return "\n\n".join(formatted_results)
            
    except Exception as e:
        return f"Error occurred during web search: {str(e)}"


# This is the tool list to pass to OpenAI API
# Format must comply with OpenAI requirements
available_tools = {
    "local_rag_search": local_rag_search,
    "web_search": web_search,
}

tools_specs = [
    {
        "type": "function",
        "function": {
            "name": "local_rag_search",
            "description": "Query internal product information or features about Gemini AI Assistant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific question or keywords to search for",
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
            "description": "Query the latest, real-time information, or topics not covered by the local knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific question or keywords to search for, e.g., 'Taipei today weather' or 'Nvidia latest stock price'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
