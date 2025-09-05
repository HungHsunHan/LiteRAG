# RRRC Chatbot - RAG + Web Search AI Assistant

一個結合 RAG（檢索增強生成）與網路搜尋功能的 AI 助理，提供本地知識庫查詢和即時資訊搜尋。

## ✨ 功能特色

- 🤖 **智能對話**：使用 OpenAI GPT-4o 模型進行自然語言對話
- 📚 **RAG 知識庫**：本地 Markdown 文檔向量化搜尋
- 🌐 **網路搜尋**：即時獲取最新資訊
- 💬 **對話記憶**：支援多輪對話上下文
- 📱 **輕量前端**：純 HTML/CSS/JS 實現，無需額外框架
- 🔄 **串流回應**：實時顯示 AI 回覆內容

## 🛠️ 技術架構

### 後端
- **FastAPI**：高效能 Web 框架
- **LangChain**：RAG 系統實現
- **FAISS**：向量相似度搜尋
- **OpenAI API**：GPT-4o 模型和文本嵌入
- **DuckDuckGo Search**：網路搜尋功能

### 前端
- **原生 HTML/CSS/JS**：輕量化實現
- **Fetch API**：處理串流回應
- **響應式設計**：適配各種設備

## 🚀 安裝與設置

### 1. 環境需求

- Python 3.8+
- Node.js（可選，用於本地開發伺服器）

### 2. 安裝依賴

```bash
# 安裝 Python 依賴
pip install fastapi uvicorn openai python-dotenv
pip install langchain langchain-openai langchain-community
pip install faiss-cpu duckduckgo-search

# 或使用 requirements.txt（如果有的話）
pip install -r requirements.txt
```

### 3. 環境變數設置

在專案根目錄創建 `.env` 檔案：

```env
# 必要設置
OPENAI_API_KEY=your_openai_api_key_here

# 可選設置（有預設值）
OPENAI_MODEL=gpt-4o
KNOWLEDGE_BASE_PATH=docs/Museum_Collection_Info.md
```

### 4. 知識庫準備

確保 `docs/Museum_Collection_Info.md` 檔案存在，或：

- 修改 `KNOWLEDGE_BASE_PATH` 環境變數指向你的 Markdown 檔案
- 檔案格式需使用標準 Markdown 標題結構（#, ##, ###）

## 🎯 執行方式

### 方法一：使用 Uvicorn（推薦）

```bash
# 在專案根目錄執行
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 方法二：直接執行 Python

```bash
# 如果你修改了 main.py 加入了 __main__ 區塊
python main.py
```

### 3. 開啟前端

有幾種方式開啟前端：

**方式 A：直接開啟檔案**
```bash
# 在瀏覽器中直接開啟
open index.html
# 或雙擊 index.html 檔案
```

**方式 B：使用簡單 HTTP 伺服器**
```bash
# Python 內建伺服器
python -m http.server 3000

# 或使用 Node.js
npx serve . -p 3000
```

然後在瀏覽器開啟：
- 後端 API：http://localhost:8000
- 前端介面：http://localhost:3000 或直接開啟 index.html

## 📋 使用說明

### 基本對話
1. 在輸入框輸入問題
2. 點擊「發送」或按 Enter
3. AI 會根據問題自動選擇使用 RAG 搜尋或網路搜尋

### 功能特性

**RAG 搜尋**：
- 當詢問與本地知識庫相關的問題時自動觸發
- 例如：「帷幕牆是什麼？」

**網路搜尋**：
- 當需要即時資訊時自動觸發  
- 例如：「今天台北天氣如何？」

**新對話**：
- 點擊「開啟新對話」按鈕清除歷史記錄

## 🔧 配置說明

### 環境變數

| 變數名稱 | 必要性 | 預設值 | 說明 |
|---------|--------|--------|------|
| `OPENAI_API_KEY` | 必要 | - | OpenAI API 金鑰 |
| `OPENAI_MODEL` | 可選 | `gpt-4o` | 使用的 OpenAI 模型 |
| `KNOWLEDGE_BASE_PATH` | 可選 | `docs/Museum_Collection_Info.md` | 知識庫檔案路徑 |

### 模型選擇

支援的 OpenAI 模型：
- `gpt-4o`（推薦）
- `gpt-4o-mini`
- `gpt-4-turbo`
- `gpt-4`

### CORS 設置

目前允許的來源：
- `http://localhost`
- `http://127.0.0.1`
- `null`（本地檔案協議）

## 🐛 常見問題

### 1. OpenAI API 錯誤
**問題**：收到 401、403 或 429 錯誤
**解決方案**：
- 檢查 `OPENAI_API_KEY` 是否正確設置
- 確認 API 金鑰有效且有足夠額度
- 檢查 API 使用限制

### 2. 知識庫初始化失敗
**問題**：RAG 搜尋返回「知識庫尚未初始化」
**解決方案**：
- 確認知識庫檔案存在且路徑正確
- 檢查檔案編碼是否為 UTF-8
- 確認檔案內容使用標準 Markdown 格式

### 3. 網路搜尋失敗
**問題**：網路搜尋返回錯誤
**解決方案**：
- 檢查網路連線
- 確認防火牆設置
- 可能需要使用代理伺服器

### 4. CORS 錯誤
**問題**：前端無法連接後端 API
**解決方案**：
- 確認前端和後端的 URL 設置
- 修改 `main.py` 中的 CORS 允許來源
- 使用相同的協議（http 或 https）

## 📁 專案結構

```
RRRC_chatbot/
├── main.py                 # FastAPI 應用主程式
├── rag_setup.py           # RAG 系統設置
├── tools.py               # 工具函數（RAG、網路搜尋）
├── index.html             # 前端界面
├── docs/
│   └── Museum_Collection_Info.md  # 知識庫檔案
├── rag_timestamp.json     # RAG 時間戳記（自動生成）
├── .env                   # 環境變數（需自行創建）
└── README.md             # 說明文檔
```

## 🔒 安全注意事項

1. **API 金鑰保護**：絕不要將 `.env` 檔案提交到版本控制
2. **CORS 設置**：生產環境中應限制允許的來源
3. **輸入驗證**：確保用戶輸入經過適當驗證
4. **速率限制**：考慮實作 API 調用頻率限制

## 📈 效能優化建議

1. **快取機制**：實作 RAG 結果快取
2. **連接池**：使用資料庫連接池
3. **非同步處理**：充分利用 FastAPI 的非同步特性
4. **CDN**：靜態資源使用 CDN 加速

## 🤝 貢獻指南

歡迎提交 Issue 和 Pull Request！

## 📄 授權

[在此添加授權資訊]

---

如有任何問題，請隨時聯繫開發團隊。