# main.py
import asyncio
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from rag_setup import setup_rag
from tools import available_tools, tools_specs


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
    "null",  # 允許從本地 file:// 協議發出的請求
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


async def stream_generator(messages: list):
    """
    處理與 OpenAI 的互動並生成串流回覆的核心函數。
    """
    # === 步驟 1: 第一次呼叫 OpenAI，判斷是否需要使用工具 ===
    try:
        first_response_stream = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=tools_specs,
            tool_choice="auto",
            stream=True,
        )

        tool_calls = {}  # 用字典來累積 tool call 片段
        # 迭代處理串流的每一個 chunk
        async for chunk in first_response_stream:
            # 如果 chunk 包含 tool_calls 的 delta，表示模型決定要呼叫工具
            if chunk.choices[0].delta.tool_calls:
                for tool_call_delta in chunk.choices[0].delta.tool_calls:
                    if tool_call_delta.id:
                        # 新的 tool call
                        if tool_call_delta.id not in tool_calls:
                            tool_calls[tool_call_delta.id] = {
                                "id": tool_call_delta.id,
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }

                        # 累積 function name 和 arguments
                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls[tool_call_delta.id]["function"][
                                    "name"
                                ] += tool_call_delta.function.name
                            if tool_call_delta.function.arguments:
                                tool_calls[tool_call_delta.id]["function"][
                                    "arguments"
                                ] += tool_call_delta.function.arguments
                    else:
                        # 如果沒有 id，可能是後續的 arguments 片段，找到最後一個 tool call
                        if (
                            tool_calls
                            and tool_call_delta.function
                            and tool_call_delta.function.arguments
                        ):
                            last_tool_id = list(tool_calls.keys())[-1]
                            tool_calls[last_tool_id]["function"][
                                "arguments"
                            ] += tool_call_delta.function.arguments

            # 如果 chunk 包含內容，直接串流出去 (模型可能在呼叫工具前回覆一些話)
            if content := chunk.choices[0].delta.content:
                yield content

        # 檢查 first_response 是否要求呼叫工具
        if not tool_calls:
            # 如果沒有工具呼叫，流程在此結束
            return

    except Exception as e:
        print(f"Error during first OpenAI call: {e}")
        yield f"[ERROR] 與 OpenAI 互動時發生錯誤: {e}"
        return

    # === 步驟 2: 如果模型決定使用工具 ===
    # 建立一個 assistant 的回覆，其中包含工具呼叫的請求
    assistant_message = {"role": "assistant", "content": None, "tool_calls": []}
    for tool_call_data in tool_calls.values():
        assistant_message["tool_calls"].append(tool_call_data)

    messages.append(assistant_message)

    # === 步驟 3: 執行工具並取得結果 ===
    tool_results = []

    for tool_call in assistant_message["tool_calls"]:
        tool_name = tool_call["function"]["name"]

        # 可以在這裡先傳送一個狀態訊息給前端
        yield f"\n\n[正在執行工具: {tool_name}...]\n\n"

        if tool_name in available_tools:
            function_to_call = available_tools[tool_name]
            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_output = function_to_call(**tool_args)

                # 暫時存儲工具結果，待所有工具成功執行後再加入 messages
                tool_result = {
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": tool_name,
                    "content": tool_output,
                }
                tool_results.append(tool_result)

            except json.JSONDecodeError as e:
                yield f"[ERROR] 工具 '{tool_name}' 的參數格式錯誤: {e}"
                return
            except Exception as e:
                yield f"[ERROR] 執行工具 '{tool_name}' 時發生錯誤: {e}"
                return
        else:
            yield f"[ERROR] 找不到工具: {tool_name}"
            return

    # 如果所有工具都成功執行，才將結果加入 messages
    messages.extend(tool_results)

    # === 步驟 4: 第二次呼叫 OpenAI，整合工具結果生成最終答案 ===
    try:
        second_response_stream = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            stream=True,
        )

        # 串流最終的回覆
        async for chunk in second_response_stream:
            if content := chunk.choices[0].delta.content:
                yield content

    except Exception as e:
        print(f"Error during second OpenAI call: {e}")
        yield f"[ERROR] 在整合工具結果時發生錯誤: {e}"


@app.post("/chat/stream")
async def chat_stream(chat_request: ChatRequest):
    """
    API 端點，接收請求並返回串流回覆。
    """
    messages = chat_request.history + [{"role": "user", "content": chat_request.query}]
    return StreamingResponse(stream_generator(messages), media_type="text/event-stream")
