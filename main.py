# main.py
import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from pydantic import BaseModel

from rag_setup import setup_rag, rag_manager
from tools import available_tools, gemini_tools


class StreamingCallbackHandler:
    """自定義回調處理器，用於捕捉工具執行事件"""

    def __init__(self, event_queue: asyncio.Queue):
        self.event_queue = event_queue

    async def on_agent_action(self, tool_name: str, tool_input: Dict[str, Any]):
        """當 Agent 決定使用工具時觸發"""
        await self.event_queue.put(
            {
                "type": "agent_action",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

    async def on_tool_end(self, tool_name: str, tool_output: str):
        """當工具執行完成時觸發"""
        await self.event_queue.put(
            {
                "type": "tool_end",
                "tool_name": tool_name,
                "tool_output": tool_output,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

    async def on_agent_finish(self, final_answer: str):
        """當 Agent 完成最終回覆時觸發"""
        await self.event_queue.put(
            {
                "type": "agent_finish",
                "final_answer": final_answer,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    # 啟動時執行
    setup_rag()
    yield
    # 關閉時執行 (如果需要的話)


app = FastAPI(lifespan=lifespan)
# 設定允許的來源
origins = [
    "http://localhost",
    "http://127.0.0.1",
    "http://192.168.0.46",  # 本機局域網IP
    "null",  # 允許從本地 file:// 協議發出的請求
    "*",  # 允許所有來源（僅用於開發測試）
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

# 載入環境變數
load_dotenv(override=True)

# 配置參數
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# 初始化 Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# 定義請求的資料結構
class ChatRequest(BaseModel):
    query: str
    history: list = []  # 支援多輪對話
    session_id: str = None  # 會話ID，用於區分不同用戶


# 定義非串流回應格式
class ChatResponse(BaseModel):
    answer: str
    tools_used: list = []
    error: Optional[str] = None
    session_id: Optional[str] = None


async def stream_generator(messages: list):
    """
    處理與 Gemini 的互動並生成 SSE 事件流的核心函數。
    """
    # 添加 RAG 系統提示
    system_instruction = """你是一個專業的RAG（檢索增強生成）助手。請嚴格遵循以下準則：

【核心原則】
1. 你只能基於搜索工具返回的結果來回答問題
2. 絕對不能編造、猜測或基於你的訓練數據提供未經搜索驗證的資訊
3. 必須明確標註所有資訊的來源

【工具使用策略】
- 對於本地知識庫相關問題，優先使用 local_rag_search
- 如果 local_rag_search 返回的結果與問題不相關或無法回答問題，必須使用 web_search 搜索網路資訊
- 對於最新資訊、即時數據、外部資訊，直接使用 web_search
- 可以同時或依序使用多個工具來獲得更全面和準確的資訊

【回答格式要求】
1. 清楚標註每個資訊的來源（知識庫 vs 網路搜尋）
2. 如果搜尋無結果，誠實告知「找不到相關資訊」
3. 不要添加未經搜索驗證的補充說明
4. 保持專業、準確、有用的回答風格

【禁止行為】
- 禁止憑空編造任何資訊
- 禁止基於常識或訓練數據直接回答（必須先搜索）
- 禁止省略資訊來源的標註

記住：你是RAG系統，資訊的可靠性和來源透明度是你的核心價值。"""

    # 轉換訊息格式為 Gemini 格式（移除 system role，使用 system_instruction）
    gemini_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            continue  # 跳過 system 訊息，使用 system_instruction 代替
        elif msg.get("role") == "user":
            gemini_messages.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg.get("role") == "assistant":
            gemini_messages.append({"role": "model", "parts": [{"text": msg["content"]}]})

    # 創建事件佇列和回調處理器
    event_queue = asyncio.Queue()
    callback_handler = StreamingCallbackHandler(event_queue)

    # === 步驟 1: 第一次呼叫 Gemini，判斷是否需要使用工具 ===
    try:
        # 設定 Gemini 配置
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[gemini_tools],
            temperature=0.3,
        )
        
        first_response_stream = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=gemini_messages,
            config=config,
        )

        function_calls = []
        has_content = False
        collected_content = ""

        # 處理第一次回覆的流
        for chunk in first_response_stream:
            # 處理文本內容
            if hasattr(chunk, 'text') and chunk.text:
                has_content = True
                collected_content += chunk.text
                yield f"data: {json.dumps({'type': 'content', 'content': chunk.text}, ensure_ascii=False)}\n\n"
            
            # 處理 function calls
            if hasattr(chunk, 'candidates') and chunk.candidates:
                candidate = chunk.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                function_calls.append(part.function_call)

        # 如果沒有工具呼叫，直接結束
        if not function_calls:
            if not has_content:
                yield f"data: {json.dumps({'type': 'content', 'content': '我理解了你的問題，但目前沒有需要額外資訊來回答。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'agent_finish', 'final_answer': collected_content}, ensure_ascii=False)}\n\n"
            return

    except Exception as e:
        print(f"Error during first Gemini call: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': f'與 Gemini 互動時發生錯誤: {e}'}, ensure_ascii=False)}\n\n"
        return

    # === 步驟 2: 執行工具並廣播事件 ===
    # 構建 function response 給 Gemini
    function_responses = []
    
    # 過濾掉無效的 function calls
    valid_function_calls = [fc for fc in function_calls if fc is not None and hasattr(fc, 'name')]
    
    for function_call in valid_function_calls:
        tool_name = function_call.name
        tool_args = dict(function_call.args) if hasattr(function_call, 'args') else {}

        try:
            # 廣播工具開始事件
            await callback_handler.on_agent_action(tool_name, tool_args)
            event = await event_queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            if tool_name in available_tools:
                function_to_call = available_tools[tool_name]
                tool_output = function_to_call(**tool_args)

                # 廣播工具完成事件
                await callback_handler.on_tool_end(tool_name, tool_output)
                event = await event_queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 構建 function response 給 Gemini
                function_responses.append({
                    "function_response": {
                        "name": tool_name,
                        "response": {"result": tool_output}
                    }
                })

            else:
                error_msg = f"找不到工具: {tool_name}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                return

        except Exception as e:
            # 工具執行異常時，記錄錯誤但繼續處理其他工具
            print(f"工具 '{tool_name}' 執行時發生錯誤: {e}")
            function_responses.append({
                "function_response": {
                    "name": tool_name,
                    "response": {"error": f"執行工具時發生錯誤: {str(e)}"}
                }
            })

    # 將 function responses 加入對話
    if function_responses:
        gemini_messages.append({
            "role": "function",
            "parts": function_responses
        })

    # === 步驟 3: 第二次呼叫 Gemini，生成最終答案 ===
    try:
        # 不需要再傳遞 tools，因為工具已經執行完畢
        final_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
        )
        
        second_response_stream = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=gemini_messages,
            config=final_config,
        )

        final_content = ""
        for chunk in second_response_stream:
            if hasattr(chunk, 'text') and chunk.text:
                final_content += chunk.text
                yield f"data: {json.dumps({'type': 'content', 'content': chunk.text}, ensure_ascii=False)}\n\n"

        # 廣播最終完成事件
        await callback_handler.on_agent_finish(final_content)
        event = await event_queue.get()
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    except Exception as e:
        print(f"Error during second Gemini call: {e}")
        error_msg = f"在整合工具結果時發生錯誤: {e}"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"


async def process_chat_request(messages: list) -> Dict[str, Any]:
    """
    處理聊天請求並返回完整回應的非串流版本
    """
    system_instruction = """你是一個專業的RAG（檢索增強生成）助手。請嚴格遵循以下準則：

【核心原則】
1. 你只能基於搜索工具返回的結果來回答問題
2. 絕對不能編造、猜測或基於你的訓練數據提供未經搜索驗證的資訊
3. 必須明確標註所有資訊的來源

【工具使用策略】
- 對於本地知識庫相關問題，優先使用 local_rag_search
- 如果 local_rag_search 返回的結果與問題不相關或無法回答問題，必須使用 web_search 搜索網路資訊
- 對於最新資訊、即時數據、外部資訊，直接使用 web_search
- 可以同時或依序使用多個工具來獲得更全面和準確的資訊

【回答格式要求】
1. 清楚標註每個資訊的來源（知識庫 vs 網路搜尋）
2. 如果搜尋無結果，誠實告知「找不到相關資訊」
3. 不要添加未經搜索驗證的補充說明
4. 保持專業、準確、有用的回答風格

【禁止行為】
- 禁止憑空編造任何資訊
- 禁止基於常識或訓練數據直接回答（必須先搜索）
- 禁止省略資訊來源的標註

記住：你是RAG系統，資訊的可靠性和來源透明度是你的核心價值。"""

    # 轉換訊息格式為 Gemini 格式
    gemini_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            continue  # 跳過 system 訊息，使用 system_instruction 代替
        elif msg.get("role") == "user":
            gemini_messages.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg.get("role") == "assistant":
            gemini_messages.append({"role": "model", "parts": [{"text": msg["content"]}]})

    tools_used = []
    final_answer = ""
    error_message = None

    try:
        # 設定 Gemini 配置
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[gemini_tools],
            temperature=0.3,
        )
        
        # 第一次呼叫 Gemini，判斷是否需要使用工具
        first_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=gemini_messages,
            config=config,
        )

        # 檢查是否有工具呼叫
        function_calls = []
        if hasattr(first_response, 'candidates') and first_response.candidates:
            candidate = first_response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call'):
                            function_calls.append(part.function_call)

        if function_calls:
            # 構建 function response 給 Gemini
            function_responses = []
            
            # 過濾掉無效的 function calls
            valid_function_calls = [fc for fc in function_calls if fc is not None and hasattr(fc, 'name')]
            
            for function_call in valid_function_calls:
                tool_name = function_call.name
                tool_args = dict(function_call.args) if hasattr(function_call, 'args') else {}
                tools_used.append({"name": tool_name, "arguments": tool_args})

                try:
                    if tool_name in available_tools:
                        function_to_call = available_tools[tool_name]
                        tool_output = function_to_call(**tool_args)

                        # 構建 function response 給 Gemini
                        function_responses.append({
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": tool_output}
                            }
                        })
                    else:
                        error_message = f"找不到工具: {tool_name}"
                        return {
                            "answer": "",
                            "tools_used": tools_used,
                            "error": error_message,
                        }

                except Exception as e:
                    error_message = f"執行工具 '{tool_name}' 時發生錯誤: {e}"
                    return {
                        "answer": "",
                        "tools_used": tools_used,
                        "error": error_message,
                    }

            # 將 function responses 加入對話
            if function_responses:
                gemini_messages.append({
                    "role": "function",
                    "parts": function_responses
                })

            # 第二次呼叫 Gemini，生成最終答案
            final_config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
            )
            
            second_response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=gemini_messages,
                config=final_config,
            )

            final_answer = second_response.text if hasattr(second_response, 'text') else "無法生成回應"

        else:
            # 沒有工具呼叫，直接使用第一次的回應
            final_answer = (
                first_response.text
                if hasattr(first_response, 'text')
                else "我理解了你的問題，但目前沒有需要額外資訊來回答。"
            )

    except Exception as e:
        error_message = f"處理請求時發生錯誤: {e}"
        return {"answer": "", "tools_used": tools_used, "error": error_message}

    return {"answer": final_answer, "tools_used": tools_used, "error": error_message}


@app.post("/chat/stream")
async def chat_stream(chat_request: ChatRequest):
    """
    API 端點，接收請求並返回 SSE 串流。
    """
    # 記錄會話ID以便調試（可選）
    if chat_request.session_id:
        print(
            f"處理會話 {chat_request.session_id} 的請求: {chat_request.query[:50]}..."
        )

    messages = chat_request.history + [{"role": "user", "content": chat_request.query}]

    return StreamingResponse(
        stream_generator(messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 對 nginx 禁用緩衝
        },
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(chat_request: ChatRequest):
    """
    API 端點，接收請求並返回完整的JSON回應（非串流）。
    """
    if chat_request.session_id:
        print(
            f"處理會話 {chat_request.session_id} 的非串流請求: {chat_request.query[:50]}..."
        )

    messages = chat_request.history + [{"role": "user", "content": chat_request.query}]

    result = await process_chat_request(messages)

    return ChatResponse(
        answer=result["answer"],
        tools_used=result["tools_used"],
        error=result["error"],
        session_id=chat_request.session_id,
    )
