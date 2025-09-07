# main.py
import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from rag_setup import setup_rag
from tools import available_tools, tools_specs


class StreamingCallbackHandler:
    """自定義回調處理器，用於捕捉工具執行事件"""
    
    def __init__(self, event_queue: asyncio.Queue):
        self.event_queue = event_queue
    
    async def on_agent_action(self, tool_name: str, tool_input: Dict[str, Any]):
        """當 Agent 決定使用工具時觸發"""
        await self.event_queue.put({
            "type": "agent_action",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def on_tool_end(self, tool_name: str, tool_output: str):
        """當工具執行完成時觸發"""
        await self.event_queue.put({
            "type": "tool_end", 
            "tool_name": tool_name,
            "tool_output": tool_output,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def on_agent_finish(self, final_answer: str):
        """當 Agent 完成最終回覆時觸發"""
        await self.event_queue.put({
            "type": "agent_finish",
            "final_answer": final_answer,
            "timestamp": asyncio.get_event_loop().time()
        })


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
    "*"  # 允許所有來源（僅用於開發測試）
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

# 載入環境變數 (OPENAI_API_KEY)
load_dotenv(override=True)

# 配置參數
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # 預設使用 gpt-4o

# 初始化 OpenAI client
client = AsyncOpenAI()


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
    處理與 OpenAI 的互動並生成 SSE 事件流的核心函數。
    """
    # 添加 RAG 系統提示
    system_prompt = {
        "role": "system",
        "content": """你是一個專業的RAG（檢索增強生成）助手。請嚴格遵循以下準則：

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
    }
    
    # 將系統提示插入到訊息列表開頭
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_prompt)
    
    # 創建事件佇列和回調處理器
    event_queue = asyncio.Queue()
    callback_handler = StreamingCallbackHandler(event_queue)
    
    # === 步驟 1: 第一次呼叫 OpenAI，判斷是否需要使用工具 ===
    try:
        first_response_stream = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=tools_specs,
            tool_choice="auto",
            stream=True,
        )

        tool_calls = {}
        has_content = False
        
        # 處理第一次回覆的流
        async for chunk in first_response_stream:
            # 處理工具呼叫
            if chunk.choices[0].delta.tool_calls:
                for tool_call_delta in chunk.choices[0].delta.tool_calls:
                    if tool_call_delta.id:
                        if tool_call_delta.id not in tool_calls:
                            tool_calls[tool_call_delta.id] = {
                                "id": tool_call_delta.id,
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }

                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls[tool_call_delta.id]["function"]["name"] += tool_call_delta.function.name
                            if tool_call_delta.function.arguments:
                                tool_calls[tool_call_delta.id]["function"]["arguments"] += tool_call_delta.function.arguments
                    else:
                        if tool_calls and tool_call_delta.function and tool_call_delta.function.arguments:
                            last_tool_id = list(tool_calls.keys())[-1]
                            tool_calls[last_tool_id]["function"]["arguments"] += tool_call_delta.function.arguments

            # 處理內容回覆
            if content := chunk.choices[0].delta.content:
                has_content = True
                yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"

        # 如果沒有工具呼叫，直接結束
        if not tool_calls:
            if not has_content:
                yield f"data: {json.dumps({'type': 'content', 'content': '我理解了你的問題，但目前沒有需要額外資訊來回答。'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'agent_finish', 'final_answer': ''}, ensure_ascii=False)}\n\n"
            return

    except Exception as e:
        print(f"Error during first OpenAI call: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': f'與 OpenAI 互動時發生錯誤: {e}'}, ensure_ascii=False)}\n\n"
        return

    # === 步驟 2: 執行工具並廣播事件 ===
    assistant_message = {"role": "assistant", "content": None, "tool_calls": list(tool_calls.values())}
    messages.append(assistant_message)

    tool_results = []

    for tool_call in assistant_message["tool_calls"]:
        tool_name = tool_call["function"]["name"]
        
        try:
            tool_args = json.loads(tool_call["function"]["arguments"])
            
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

                tool_results.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_output,
                })

            else:
                error_msg = f"找不到工具: {tool_name}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                return

        except json.JSONDecodeError as e:
            error_msg = f"工具 '{tool_name}' 的參數格式錯誤: {e}"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
            return
        except Exception as e:
            # 工具執行異常時，記錄錯誤但繼續處理其他工具
            print(f"工具 '{tool_name}' 執行時發生錯誤: {e}")
            tool_results.append({
                "tool_call_id": tool_call["id"],
                "role": "tool",
                "name": tool_name,
                "content": f"執行工具時發生錯誤: {str(e)}",
            })
            # 不要 return，繼續處理其他工具

    # 將工具結果加入對話
    messages.extend(tool_results)

    # === 步驟 3: 第二次呼叫 OpenAI，生成最終答案 ===
    try:
        second_response_stream = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            stream=True,
        )

        final_content = ""
        async for chunk in second_response_stream:
            if content := chunk.choices[0].delta.content:
                final_content += content
                yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"

        # 廣播最終完成事件
        await callback_handler.on_agent_finish(final_content)
        event = await event_queue.get()
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    except Exception as e:
        print(f"Error during second OpenAI call: {e}")
        error_msg = f"在整合工具結果時發生錯誤: {e}"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"


async def process_chat_request(messages: list) -> Dict[str, Any]:
    """
    處理聊天請求並返回完整回應的非串流版本
    """
    system_prompt = {
        "role": "system",
        "content": """你是一個專業的RAG（檢索增強生成）助手。請嚴格遵循以下準則：

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
    }
    
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_prompt)
    
    tools_used = []
    final_answer = ""
    error_message = None
    
    try:
        # 第一次呼叫 OpenAI，判斷是否需要使用工具
        first_response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=tools_specs,
            tool_choice="auto",
        )

        # 檢查是否有工具呼叫
        if first_response.choices[0].message.tool_calls:
            # 處理工具呼叫
            assistant_message = {
                "role": "assistant", 
                "content": first_response.choices[0].message.content,
                "tool_calls": first_response.choices[0].message.tool_calls
            }
            messages.append(assistant_message)
            
            tool_results = []
            
            for tool_call in assistant_message["tool_calls"]:
                tool_name = tool_call.function.name
                
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                    tools_used.append({
                        "name": tool_name,
                        "arguments": tool_args
                    })
                    
                    if tool_name in available_tools:
                        function_to_call = available_tools[tool_name]
                        tool_output = function_to_call(**tool_args)
                        
                        tool_results.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_name,
                            "content": tool_output,
                        })
                    else:
                        error_message = f"找不到工具: {tool_name}"
                        return {
                            "answer": "",
                            "tools_used": tools_used,
                            "error": error_message
                        }
                        
                except json.JSONDecodeError as e:
                    error_message = f"工具 '{tool_name}' 的參數格式錯誤: {e}"
                    return {
                        "answer": "",
                        "tools_used": tools_used,
                        "error": error_message
                    }
                except Exception as e:
                    error_message = f"執行工具 '{tool_name}' 時發生錯誤: {e}"
                    return {
                        "answer": "",
                        "tools_used": tools_used,
                        "error": error_message
                    }
            
            # 將工具結果加入對話
            messages.extend(tool_results)
            
            # 第二次呼叫 OpenAI，生成最終答案
            second_response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
            )
            
            final_answer = second_response.choices[0].message.content
            
        else:
            # 沒有工具呼叫，直接使用第一次的回應
            final_answer = first_response.choices[0].message.content or "我理解了你的問題，但目前沒有需要額外資訊來回答。"
    
    except Exception as e:
        error_message = f"處理請求時發生錯誤: {e}"
        return {
            "answer": "",
            "tools_used": tools_used,
            "error": error_message
        }
    
    return {
        "answer": final_answer,
        "tools_used": tools_used,
        "error": error_message
    }


@app.post("/chat/stream")
async def chat_stream(chat_request: ChatRequest):
    """
    API 端點，接收請求並返回 SSE 串流。
    """
    # 記錄會話ID以便調試（可選）
    if chat_request.session_id:
        print(f"處理會話 {chat_request.session_id} 的請求: {chat_request.query[:50]}...")
    
    messages = chat_request.history + [{"role": "user", "content": chat_request.query}]
    
    return StreamingResponse(
        stream_generator(messages), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 對 nginx 禁用緩衝
        }
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(chat_request: ChatRequest):
    """
    API 端點，接收請求並返回完整的JSON回應（非串流）。
    """
    if chat_request.session_id:
        print(f"處理會話 {chat_request.session_id} 的非串流請求: {chat_request.query[:50]}...")
    
    messages = chat_request.history + [{"role": "user", "content": chat_request.query}]
    
    result = await process_chat_request(messages)
    
    return ChatResponse(
        answer=result["answer"],
        tools_used=result["tools_used"],
        error=result["error"],
        session_id=chat_request.session_id
    )
