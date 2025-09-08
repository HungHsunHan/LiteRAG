#!/usr/bin/env python3
"""
啟動腳本 - 自動配置並啟動 RAG 聊天機器人伺服器
"""

import socket
import threading
import uvicorn
import http.server
import socketserver
import ssl
import os
import subprocess
import sys

def get_local_ip():
    """獲取本機局域網IP地址"""
    try:
        # 創建一個 socket 連接到外部地址來獲取本機IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def ensure_certificates():
    """確保SSL憑證存在，如果不存在則自動生成"""
    cert_file = "server.crt"
    key_file = "server.key"
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("✓ SSL憑證已存在")
        return True
    
    print("⚠️  未找到SSL憑證，正在自動生成...")
    try:
        # 執行憑證生成腳本
        result = subprocess.run([sys.executable, "generate_cert.py"], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ SSL憑證生成成功")
            return True
        else:
            print(f"❌ 憑證生成失敗: {result.stderr}")
            print("🔧 請手動執行: python generate_cert.py")
            return False
    except Exception as e:
        print(f"❌ 執行憑證生成時出錯: {e}")
        print("🔧 請手動執行: python generate_cert.py")
        return False

def start_frontend_server():
    """啟動前端HTTPS伺服器"""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("0.0.0.0", 3000), handler) as httpd:
        # 配置 SSL
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain('server.crt', 'server.key')
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        httpd.serve_forever()

if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"🚀 正在啟動 RAG 聊天機器人伺服器...")
    print(f"📍 本機IP地址: {local_ip}")
    print("-" * 50)
    
    # 確保SSL憑證存在
    if not ensure_certificates():
        print("❌ SSL憑證設置失敗，將無法使用HTTPS")
        print("💡 仍可以使用HTTP，但語音功能將不可用")
    
    print("-" * 50)
    print(f"🖥️  後端API:")
    print(f"   HTTPS本地: https://127.0.0.1:8000")
    print(f"   HTTPS局域網: https://{local_ip}:8000")
    print("-" * 50)
    print(f"🌐 前端網頁:")
    print(f"   HTTPS本地: https://localhost:3000")
    print(f"   HTTPS局域網: https://{local_ip}:3000")
    print(f"   HTTP本地: http://localhost:3001 (備用)")
    print("-" * 50)
    print("🔒 語音功能需要 HTTPS 環境，請使用 HTTPS 連結！")
    print("-" * 50)
    print(f"⏹️  按 Ctrl+C 停止所有伺服器")
    print("-" * 50)
    
    # 啟動前端HTTPS伺服器（在背景執行緒中）
    frontend_thread = threading.Thread(target=start_frontend_server, daemon=True)
    frontend_thread.start()
    
    # 啟動備用HTTP前端伺服器（在背景執行緒中）
    def start_http_frontend():
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("0.0.0.0", 3001), handler) as httpd:
            httpd.serve_forever()
    
    http_frontend_thread = threading.Thread(target=start_http_frontend, daemon=True)
    http_frontend_thread.start()
    
    # 啟動後端HTTPS API伺服器（主執行緒）
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000,
        ssl_keyfile="server.key",
        ssl_certfile="server.crt",
        reload=True,  # 開發模式，程式碼變更時自動重載
        log_level="info"
    )