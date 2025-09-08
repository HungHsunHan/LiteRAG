#!/usr/bin/env python3
"""
自動生成自簽SSL憑證的工具腳本
用於支援WebRTC功能所需的HTTPS連接
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta

def check_openssl():
    """檢查系統是否有OpenSSL"""
    try:
        result = subprocess.run(['openssl', 'version'], 
                              capture_output=True, text=True, check=True)
        print(f"✓ 找到 OpenSSL: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ 找不到 OpenSSL，請先安裝 OpenSSL")
        return False

def generate_certificate():
    """生成自簽SSL憑證"""
    cert_file = "server.crt"
    key_file = "server.key"
    
    # 檢查憑證是否已存在
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("✓ SSL憑證已存在")
        return True
    
    if not check_openssl():
        return False
    
    print("🔐 正在生成自簽SSL憑證...")
    
    # 生成私鑰和憑證的OpenSSL命令
    openssl_cmd = [
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-keyout', key_file,
        '-out', cert_file,
        '-days', '365',
        '-nodes',
        '-subj', '/C=TW/ST=Taiwan/L=Taipei/O=RRRC Chatbot/CN=localhost'
    ]
    
    try:
        subprocess.run(openssl_cmd, check=True)
        print("✓ SSL憑證生成成功!")
        print(f"  - 憑證檔案: {cert_file}")
        print(f"  - 私鑰檔案: {key_file}")
        print(f"  - 有效期限: 365天")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 憑證生成失敗: {e}")
        return False

def show_certificate_info():
    """顯示憑證資訊"""
    cert_file = "server.crt"
    
    if not os.path.exists(cert_file):
        return
    
    try:
        result = subprocess.run([
            'openssl', 'x509', '-in', cert_file, '-text', '-noout'
        ], capture_output=True, text=True, check=True)
        
        # 提取有效期限資訊
        for line in result.stdout.split('\n'):
            if 'Not After' in line:
                print(f"📅 憑證到期時間: {line.strip()}")
                break
    except subprocess.CalledProcessError:
        pass

if __name__ == "__main__":
    print("🔧 RRRC Chatbot SSL憑證生成工具")
    print("=" * 40)
    
    success = generate_certificate()
    
    if success:
        show_certificate_info()
        print("\n💡 注意事項:")
        print("  - 這是自簽憑證，瀏覽器會顯示安全警告")
        print("  - 點擊「繼續前往」或「Advanced」→「Proceed to localhost」即可")
        print("  - WebRTC語音功能需要HTTPS才能正常工作")
    else:
        print("\n❌ 憑證生成失敗")
        sys.exit(1)