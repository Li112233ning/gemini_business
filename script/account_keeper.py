#!/usr/bin/env python3
"""
Gemini Business 账号守护脚本

功能：
1. 定时检测所有账号是否可用
2. 删除不可用账号
3. 当可用账号 < MIN_ACCOUNTS 时，自动注册补充

配置（环境变量）：
- MIN_ACCOUNTS: 最少保持账号数（默认 5）
- CHECK_INTERVAL: 检测间隔秒数（默认 3600，即1小时）
- ACCOUNTS_DIR: 账号目录（默认 data/accounts）

使用方式：
    python account_keeper.py
"""

import os
import sys
import time
import json
import glob
import subprocess
from datetime import datetime
from typing import List, Dict, Optional

import requests

# 添加项目根目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

# ========== 配置 ==========
MIN_ACCOUNTS = int(os.environ.get("MIN_ACCOUNTS", 5))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 3600))
ACCOUNTS_DIR = os.environ.get("ACCOUNTS_DIR", os.path.join(PROJECT_ROOT, "data", "accounts"))

# Gemini Business API 测试 URL
GEMINI_API_URL = "https://business.gemini.google/v1beta/models"


def log(msg: str, level: str = "INFO"):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}][{level}] {msg}")


def load_accounts() -> List[Dict]:
    """加载所有账号配置"""
    accounts = []
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    
    for file_path in glob.glob(os.path.join(ACCOUNTS_DIR, "*.json")):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                account = json.load(f)
                account['_file_path'] = file_path
                accounts.append(account)
        except Exception as e:
            log(f"加载账号失败 {file_path}: {e}", "ERR")
    
    return accounts


def check_account(account: Dict) -> bool:
    """检测账号是否可用"""
    try:
        # 构建 cookies
        cookies = {
            "__Secure-C_SES": account.get("secure_c_ses", ""),
            "__Host-C_OSES": account.get("host_c_oses", ""),
        }
        
        # 构建请求参数
        params = {
            "csesidx": account.get("csesidx", ""),
        }
        
        # 发送测试请求
        response = requests.get(
            GEMINI_API_URL,
            cookies=cookies,
            params=params,
            timeout=30
        )
        
        # 200 表示账号有效
        if response.status_code == 200:
            return True
        
        # 401/403 表示账号失效
        if response.status_code in [401, 403]:
            log(f"账号失效 {account.get('id')}: HTTP {response.status_code}", "WARN")
            return False
        
        # 其他状态码，暂时认为有效（可能是临时错误）
        log(f"账号检测异常 {account.get('id')}: HTTP {response.status_code}", "WARN")
        return True
        
    except Exception as e:
        log(f"账号检测失败 {account.get('id')}: {e}", "ERR")
        # 网络错误时暂时认为有效
        return True


def delete_account(account: Dict):
    """删除账号配置文件"""
    file_path = account.get('_file_path')
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            log(f"已删除失效账号: {account.get('id')}")
        except Exception as e:
            log(f"删除账号失败 {account.get('id')}: {e}", "ERR")


def register_accounts(count: int):
    """调用注册脚本补充账号"""
    if count <= 0:
        return
    
    log(f"开始注册 {count} 个新账号...")
    
    try:
        # 调用注册脚本
        env = os.environ.copy()
        env["TOTAL_ACCOUNTS"] = str(count)
        env["OUTPUT_DIR"] = ACCOUNTS_DIR
        
        register_script = os.path.join(SCRIPT_DIR, "register_accounts.py")
        
        # 使用 Popen 实时输出日志
        process = subprocess.Popen(
            [sys.executable, "-u", register_script],
            env=env,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )
        
        # 实时读取并输出
        for line in process.stdout:
            print(line, end='', flush=True)
        
        process.wait()
        
        if process.returncode == 0:
            log(f"注册完成")
        else:
            log(f"注册脚本返回错误码: {process.returncode}", "WARN")
            
    except Exception as e:
        log(f"注册账号异常: {e}", "ERR")


def check_and_maintain():
    """检测并维护账号"""
    log("=" * 50)
    log("开始账号检测与维护")
    
    # 加载账号
    accounts = load_accounts()
    log(f"当前账号数: {len(accounts)}")
    
    # 检测每个账号
    valid_accounts = []
    for account in accounts:
        account_id = account.get('id', 'unknown')
        log(f"检测账号: {account_id}")
        
        if check_account(account):
            valid_accounts.append(account)
            log(f"  ✓ 有效")
        else:
            delete_account(account)
            log(f"  ✗ 已删除")
    
    valid_count = len(valid_accounts)
    log(f"有效账号数: {valid_count}/{MIN_ACCOUNTS}")
    
    # 补充账号
    if valid_count < MIN_ACCOUNTS:
        need_count = MIN_ACCOUNTS - valid_count
        log(f"需要补充 {need_count} 个账号")
        register_accounts(need_count)
    else:
        log("账号数量充足，无需补充")
    
    log("检测完成")
    log("=" * 50)


def main():
    log("=" * 50)
    log("Gemini Business 账号守护服务启动")
    log(f"最少账号数: {MIN_ACCOUNTS}")
    log(f"检测间隔: {CHECK_INTERVAL} 秒")
    log(f"账号目录: {ACCOUNTS_DIR}")
    log("=" * 50)
    
    while True:
        try:
            check_and_maintain()
        except Exception as e:
            log(f"维护异常: {e}", "ERR")
        
        log(f"等待 {CHECK_INTERVAL} 秒后进行下次检测...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
