#!/usr/bin/env python3
"""
啟動腳本 - 自動配置並啟動 RAG 聊天機器人伺服器
"""

import socket
import threading
import uvicorn
import http.server
import socketserver
import os

def get_local_ip():
    """獲取本機局域網IP地址"""
    try:
        # 創建一個 socket 連接到外部地址來獲取本機IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def start_frontend_server():
    """啟動前端HTTP伺服器"""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("0.0.0.0", 3000), handler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"🚀 正在啟動 RAG 聊天機器人伺服器...")
    print(f"📍 本機IP地址: {local_ip}")
    print("-" * 50)
    print(f"🖥️  後端API:")
    print(f"   本地: http://127.0.0.1:8000")
    print(f"   局域網: http://{local_ip}:8000")
    print("-" * 50)
    print(f"🌐 前端網頁:")
    print(f"   本地: http://localhost:3000")
    print(f"   局域網: http://{local_ip}:3000")
    print("-" * 50)
    print(f"⏹️  按 Ctrl+C 停止所有伺服器")
    print("-" * 50)
    
    # 啟動前端伺服器（在背景執行緒中）
    frontend_thread = threading.Thread(target=start_frontend_server, daemon=True)
    frontend_thread.start()
    
    # 啟動後端API伺服器（主執行緒）
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000,
        reload=True,  # 開發模式，程式碼變更時自動重載
        log_level="info"
    )