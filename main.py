# main.py
import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from rag_setup import setup_rag
from tools import available_tools, tools_specs


class StreamingCallbackHandler:
    """Custom callback handler for capturing tool execution events"""
    
    def __init__(self, event_queue: asyncio.Queue):
        self.event_queue = event_queue
    
    async def on_agent_action(self, tool_name: str, tool_input: Dict[str, Any]):
        """Triggered when Agent decides to use a tool"""
        await self.event_queue.put({
            "type": "agent_action",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def on_tool_end(self, tool_name: str, tool_output: str):
        """Triggered when tool execution is completed"""
        await self.event_queue.put({
            "type": "tool_end", 
            "tool_name": tool_name,
            "tool_output": tool_output,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def on_agent_finish(self, final_answer: str):
        """Triggered when Agent completes final response"""
        await self.event_queue.put({
            "type": "agent_finish",
            "final_answer": final_answer,
            "timestamp": asyncio.get_event_loop().time()
        })


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Execute on startup
    setup_rag()
    yield
    # Execute on shutdown (if needed)


app = FastAPI(lifespan=lifespan)
# Configure allowed origins
origins = [
    "http://localhost",
    "http://127.0.0.1",
    "null",  # Allow requests from local file:// protocol
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Load environment variables (OPENAI_API_KEY)
load_dotenv(override=True)

# Configuration parameters
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # Default to gpt-4o

# Initialize OpenAI client
client = AsyncOpenAI()


# Define request data structure
class ChatRequest(BaseModel):
    query: str
    history: list = []  # Support multi-turn conversation


async def stream_generator(messages: list):
    """
    Core function to handle OpenAI interaction and generate SSE event stream.
    """
    # Create event queue and callback handler
    event_queue = asyncio.Queue()
    callback_handler = StreamingCallbackHandler(event_queue)
    
    # === Step 1: First OpenAI call to determine if tools are needed ===
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
        
        # Process first response stream
        async for chunk in first_response_stream:
            # Handle tool calls
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

            # Handle content response
            if content := chunk.choices[0].delta.content:
                has_content = True
                yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"

        # If no tool calls, end directly
        if not tool_calls:
            if not has_content:
                yield f"data: {json.dumps({'type': 'content', 'content': 'I understand your question, but no additional information is needed to answer it.'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'agent_finish', 'final_answer': ''}, ensure_ascii=False)}\n\n"
            return

    except Exception as e:
        print(f"Error during first OpenAI call: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': f'Error interacting with OpenAI: {e}'}, ensure_ascii=False)}\n\n"
        return

    # === Step 2: Execute tools and broadcast events ===
    assistant_message = {"role": "assistant", "content": None, "tool_calls": list(tool_calls.values())}
    messages.append(assistant_message)

    tool_results = []

    for tool_call in assistant_message["tool_calls"]:
        tool_name = tool_call["function"]["name"]
        
        try:
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            # Broadcast tool start event
            await callback_handler.on_agent_action(tool_name, tool_args)
            event = await event_queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            if tool_name in available_tools:
                function_to_call = available_tools[tool_name]
                tool_output = function_to_call(**tool_args)

                # Broadcast tool completion event
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
                error_msg = f"Tool not found: {tool_name}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                return

        except json.JSONDecodeError as e:
            error_msg = f"Invalid parameter format for tool '{tool_name}': {e}"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
            return
        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {e}"
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
            return

    # Add tool results to conversation
    messages.extend(tool_results)

    # === Step 3: Second OpenAI call to generate final answer ===
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

        # Broadcast final completion event
        await callback_handler.on_agent_finish(final_content)
        event = await event_queue.get()
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    except Exception as e:
        print(f"Error during second OpenAI call: {e}")
        error_msg = f"Error integrating tool results: {e}"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(chat_request: ChatRequest):
    """
    API endpoint to receive requests and return SSE stream.
    """
    messages = chat_request.history + [{"role": "user", "content": chat_request.query}]
    
    return StreamingResponse(
        stream_generator(messages), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )
