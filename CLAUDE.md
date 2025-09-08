# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Environment
**Required**: `C:\Users\hunghsun\AppData\Local\anaconda3\envs\llm`

## Development Commands

### Server Startup
```bash
# Activate environment and start backend API server
source /usr/local/Caskroom/miniforge/base/etc/profile.d/conda.sh && conda activate llm && uvicorn main:app --host 0.0.0.0 --port 8000

# Or use the convenience script (starts both backend and frontend)
python start_server.py
```

### Frontend Access
- **Direct file**: Open `index.html` in browser
- **HTTP server**: `python -m http.server 3000` or `npx serve . -p 3000`
- **URLs**: Backend `http://localhost:8000`, Frontend `http://localhost:3000`

### Dependencies Installation
```bash
pip install fastapi uvicorn openai python-dotenv
pip install langchain langchain-openai langchain-community
pip install faiss-cpu duckduckgo-search
```

### Environment Configuration
Create `.env` file (use `.env.example` as template):
```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o
KNOWLEDGE_BASE_PATH=docs/Museum_Collection_Info.md
```

## Architecture Overview

### Core System
**RAG Chatbot** with streaming responses, dual tool system, and real-time web interface.

### Backend Architecture (`main.py`)
- **FastAPI**: Streaming SSE API endpoint `/chat/stream`
- **OpenAI Integration**: GPT-4o with function calling for tools
- **Streaming Pattern**: Two-phase OpenAI calls (tool decision → tool execution → final response)
- **Event System**: Custom callback handler streams tool execution events to frontend

### RAG System (`rag_setup.py`)
- **LangChain + FAISS**: Vector store with OpenAI embeddings (`text-embedding-3-small`)
- **Auto Re-indexing**: Checks file timestamps, rebuilds only when knowledge base changes
- **Markdown Processing**: MarkdownHeaderTextSplitter for structured chunking
- **Timestamp Tracking**: `rag_timestamp.json` prevents unnecessary re-embedding

### Tool System (`tools.py`)
- **Dual Tools**: `local_rag_search` (knowledge base) + `web_search` (DuckDuckGo)
- **Automatic Selection**: OpenAI determines tool usage based on query
- **Structured Output**: Tools return formatted results with source attribution

### Frontend (`index.html`)
- **Pure HTML/CSS/JS**: No framework dependencies
- **Streaming Interface**: Fetch API handles SSE responses
- **Tool Visualization**: Dedicated panel shows tool execution details
- **Markdown Rendering**: Uses marked.js for AI response formatting

### Knowledge Base
- **Format**: Markdown with hierarchical headers (`#`, `##`, `###`)
- **Default Location**: `docs/Museum_Collection_Info.md`
- **Content**: Museum collection information in Chinese/English
- **Processing**: Splits by headers, maintains metadata for source attribution

## Key Files

### Core Application
- `main.py`: FastAPI server with streaming chat endpoint
- `tools.py`: RAG and web search tool implementations
- `rag_setup.py`: Vector store initialization and management
- `index.html`: Complete frontend application

### Configuration & Data
- `.env`: Environment variables (create from `.env.example`)
- `docs/Museum_Collection_Info.md`: Knowledge base content
- `rag_timestamp.json`: Auto-generated timestamp for re-indexing logic

### Utilities
- `start_server.py`: Combined backend/frontend server launcher

## Development Notes

### CORS Configuration
Currently allows all origins (`*`) for development. In `main.py:63-69`, modify `origins` list for production.

### Streaming Response Pattern
The system uses a two-phase approach:
1. **Phase 1**: OpenAI decides which tools to use
2. **Tool Execution**: Execute tools and stream events to frontend
3. **Phase 2**: OpenAI generates final response using tool results

### Tool Execution Events
Frontend receives these SSE event types:
- `agent_action`: Tool execution starts
- `tool_end`: Tool execution completes
- `content`: Streaming response content
- `agent_finish`: Final response complete
- `error`: Error occurred

### Knowledge Base Updates
RAG system automatically detects file changes and re-indexes. No manual intervention required when updating `docs/Museum_Collection_Info.md`.