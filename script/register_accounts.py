#!/usr/bin/env python3
"""
Gemini Business 账号批量注册脚本

功能：
1. 使用 Selenium 自动化注册 Gemini Business 账号
2. 通过临时邮箱 API 获取验证码
3. 保存账号配置到本地 data 目录

配置（环境变量）：
- TOTAL_ACCOUNTS: 注册账号数量（默认 1）
- MAIL_API: 临时邮箱 API 地址
- MAIL_KEY: 临时邮箱 API 密钥
- OUTPUT_DIR: 输出目录（默认 data/accounts）

使用方式：
    python register_accounts.py
    TOTAL_ACCOUNTS=5 python register_accounts.py
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import time, random, json, os, sys
import requests

# Docker 环境检测
IS_DOCKER = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER', False)

# 添加项目根目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

# ========== 配置 (支持环境变量) ==========
TOTAL_ACCOUNTS = int(os.environ.get("TOTAL_ACCOUNTS", 1))
MAIL_API = os.environ.get("MAIL_API", "https://mail.chatgpt.org.uk")
MAIL_KEY = os.environ.get("MAIL_KEY", "gpt-test")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(PROJECT_ROOT, "data", "accounts"))
LOGIN_URL = "https://auth.business.gemini.google/login?continueUrl=https:%2F%2Fbusiness.gemini.google%2F&wiffid=CAoSJDIwNTlhYzBjLTVlMmMtNGUxZC1hY2JkLThmOGY2ZDE0ODM1Mg"

# XPath
XPATH = {
    "email_input": "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[1]/div[1]/div/span[2]/input",
    "continue_btn": "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/button",
    "verify_btn": "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/div[1]/span/div[1]/button",
}

NAMES = ["James Smith", "John Johnson", "Robert Williams", "Michael Brown", "William Jones",
         "David Garcia", "Mary Miller", "Patricia Davis", "Jennifer Rodriguez", "Linda Martinez"]


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}][{level}] {msg}")


def create_chrome_driver():
    """创建 Chrome 驱动 (Docker 兼容)"""
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    if IS_DOCKER:
        options.binary_location = '/usr/bin/google-chrome'
    
    return webdriver.Chrome(options=options)


def create_email():
    """创建临时邮箱"""
    try:
        r = requests.get(f"{MAIL_API}/api/generate-email",
            headers={"X-API-Key": MAIL_KEY}, timeout=30)
        if r.status_code == 200 and r.json().get('success'):
            email = r.json()['data']['email']
            log(f"邮箱创建: {email}")
            return email
        else:
            log(f"邮箱API返回: {r.status_code} - {r.text[:200]}", "ERR")
    except Exception as e:
        log(f"创建邮箱异常: {e}", "ERR")
    return None


def get_code(email, timeout=30):
    """获取验证码"""
    log(f"等待验证码 (最多{timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{MAIL_API}/api/emails", params={"email": email},
                headers={"X-API-Key": MAIL_KEY}, timeout=30)
            if r.status_code == 200:
                emails = r.json().get('data', {}).get('emails', [])
                if emails:
                    html = emails[0].get('html_content') or emails[0].get('content', '')
                    soup = BeautifulSoup(html, 'html.parser')
                    span = soup.find('span', class_='verification-code')
                    if span:
                        code = span.get_text().strip()
                        if len(code) == 6:
                            log(f"验证码: {code}")
                            return code
        except:
            pass
        print(f"  等待中... ({int(time.time()-start)}s)", end='\r')
        time.sleep(2)
    log("验证码超时", "ERR")
    return None


def save_config(email, driver, timeout=15):
    """保存配置，带轮询等待所有字段"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    log(f"等待配置数据 (最多{timeout}s)...")
    start = time.time()
    data = None

    while time.time() - start < timeout:
        cookies = driver.get_cookies()
        url = driver.current_url
        parsed = urlparse(url)

        # 解析 config_id
        path_parts = url.split('/')
        config_id = None
        for i, p in enumerate(path_parts):
            if p == 'cid' and i+1 < len(path_parts):
                config_id = path_parts[i+1].split('?')[0]
                break

        # 获取 cookies
        cookie_dict = {c['name']: c for c in cookies}
        ses_cookie = cookie_dict.get('__Secure-C_SES', {})
        host_cookie = cookie_dict.get('__Host-C_OSES', {})

        # 获取 csesidx
        csesidx = parse_qs(parsed.query).get('csesidx', [None])[0]

        # 检查所有关键字段是否都有值
        if (ses_cookie.get('value') and
            host_cookie.get('value') and
            csesidx and
            config_id):

            data = {
                "id": email,
                "csesidx": csesidx,
                "config_id": config_id,
                "secure_c_ses": ses_cookie.get('value'),
                "host_c_oses": host_cookie.get('value'),
                "expires_at": datetime.fromtimestamp(ses_cookie.get('expiry', 0) - 43200).strftime('%Y-%m-%d %H:%M:%S') if ses_cookie.get('expiry') else None
            }
            log(f"配置数据已就绪 ({time.time() - start:.1f}s)")
            break

        time.sleep(1)

    if not data:
        # 最后一次尝试，记录缺失字段
        cookies = driver.get_cookies()
        url = driver.current_url
        parsed = urlparse(url)
        cookie_dict = {c['name']: c for c in cookies}

        missing = []
        if not cookie_dict.get('__Secure-C_SES', {}).get('value'):
            missing.append('secure_c_ses')
        if not cookie_dict.get('__Host-C_OSES', {}).get('value'):
            missing.append('host_c_oses')
        if not parse_qs(parsed.query).get('csesidx', [None])[0]:
            missing.append('csesidx')

        path_parts = url.split('/')
        has_config_id = False
        for i, p in enumerate(path_parts):
            if p == 'cid' and i+1 < len(path_parts):
                has_config_id = True
                break
        if not has_config_id:
            missing.append('config_id')

        log(f"配置不完整，缺失字段: {', '.join(missing)}，跳过: {email}", "WARN")
        return None

    file_path = os.path.join(OUTPUT_DIR, f"{email}.json")
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"已保存: {file_path}")
    return data


def delete_local_file(email):
    """删除本地账号文件（仅用于失败情况）"""
    if not email:
        return
    file_path = os.path.join(OUTPUT_DIR, f"{email}.json")
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            log(f"已删除失败账号文件: {email}.json")
    except Exception as e:
        log(f"删除文件失败: {email}.json - {e}", "WARN")


def register(driver):
    """注册单个账号"""
    email = create_email()
    if not email:
        log("邮箱创建失败", "ERR")
        return None, False, None

    wait = WebDriverWait(driver, 60)

    try:
        # 1. 访问登录页
        log(f"访问登录页: {LOGIN_URL[:50]}...")
        driver.get(LOGIN_URL)
        time.sleep(2)
    except Exception as e:
        log(f"访问登录页失败: {e}", "ERR")
        return email, False, None

    # 2. 输入邮箱
    log("输入邮箱...")
    inp = wait.until(EC.visibility_of_element_located((By.XPATH, XPATH["email_input"])))
    inp.click()
    time.sleep(0.3)
    inp.clear()
    time.sleep(0.3)
    for c in email:
        inp.send_keys(c)
        time.sleep(0.05)
    log(f"邮箱: {email}, 实际值: {inp.get_attribute('value')}")
    time.sleep(0.5)

    # 3. 点击继续
    btn = wait.until(EC.element_to_be_clickable((By.XPATH, XPATH["continue_btn"])))
    driver.execute_script("arguments[0].click();", btn)
    log("点击继续")
    time.sleep(1.5)

    # 4. 获取验证码
    code = get_code(email)
    if not code:
        return email, False, None

    # 5. 输入验证码
    time.sleep(1)
    log(f"输入验证码: {code}")
    try:
        pin = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput']")))
        pin.click()
        time.sleep(0.2)
        for c in code:
            pin.send_keys(c)
            time.sleep(0.1)
    except:
        try:
            span = driver.find_element(By.CSS_SELECTOR, "span[data-index='0']")
            span.click()
            time.sleep(0.3)
            driver.switch_to.active_element.send_keys(code)
        except Exception as e:
            log(f"验证码输入失败: {e}", "ERR")
            return email, False, None

    # 6. 点击验证
    time.sleep(1)
    try:
        vbtn = driver.find_element(By.XPATH, XPATH["verify_btn"])
        driver.execute_script("arguments[0].click();", vbtn)
    except:
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            if '验证' in btn.text:
                driver.execute_script("arguments[0].click();", btn)
                break
    log("点击验证")
    time.sleep(2)

    # 7. 输入姓名
    try:
        name_inp = WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[formcontrolname='fullName'], input[placeholder='全名'], input#mat-input-0")))
        name = random.choice(NAMES)
        name_inp.clear()
        time.sleep(0.3)
        for c in name:
            name_inp.send_keys(c)
            time.sleep(0.03)
        log(f"姓名: {name}")
        name_inp.send_keys(Keys.ENTER)
    except Exception as e:
        log(f"姓名输入异常: {e}", "WARN")

    # 8. 等待进入工作台
    log("等待工作台...")
    time.sleep(2)
    for _ in range(20):
        if 'business.gemini.google' in driver.current_url and 'auth' not in driver.current_url:
            break
        time.sleep(1)
    time.sleep(1)

    # 9. 保存配置
    config = save_config(email, driver)
    if config:
        log(f"注册成功: {email}")
        return email, True, config
    return email, False, None


def main():
    print(f"\n{'='*50}")
    print(f"Gemini Business 批量注册 - 目标 {TOTAL_ACCOUNTS} 个")
    print(f"模式: 无限重试直到成功")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"{'='*50}\n")

    driver = create_chrome_driver()
    success = 0
    total_attempts = 0

    while success < TOTAL_ACCOUNTS:
        attempt_for_current = 0

        while True:  # 无限重试直到成功
            total_attempts += 1
            attempt_for_current += 1

            print(f"\n{'#'*40}")
            print(f"注册第 {success + 1}/{TOTAL_ACCOUNTS} 个账号 (第 {attempt_for_current} 次尝试)")
            print(f"{'#'*40}\n")

            try:
                driver.current_url  # 检查driver是否有效
            except:
                driver = create_chrome_driver()

            email = None
            try:
                email, ok, cfg = register(driver)
                if ok and cfg:
                    success += 1
                    log(f"账号已保存到本地: {email}")
                    break  # 成功，跳出重试循环
                else:
                    # 注册失败，删除可能存在的临时文件
                    delete_local_file(email)
                    log(f"注册失败，继续重试...", "WARN")
            except Exception as e:
                log(f"异常: {e}", "ERR")
                delete_local_file(email)
                try:
                    driver.quit()
                except:
                    pass
                driver = create_chrome_driver()
                log(f"发生异常，继续重试...", "WARN")

            print(f"\n进度: 成功 {success}/{TOTAL_ACCOUNTS} | 总尝试 {total_attempts}")

            try:
                driver.delete_all_cookies()
            except:
                pass
            time.sleep(random.randint(5, 10))

        # 成功后准备下一个
        print(f"\n进度: 成功 {success}/{TOTAL_ACCOUNTS} | 总尝试 {total_attempts}")
        if success < TOTAL_ACCOUNTS:
            try:
                driver.delete_all_cookies()
            except:
                pass
            time.sleep(random.randint(5, 10))

    try:
        driver.quit()
    except:
        pass

    print(f"\n{'='*50}")
    print(f"完成! 成功: {success}/{TOTAL_ACCOUNTS}, 总尝试: {total_attempts}")
    print(f"账号保存位置: {OUTPUT_DIR}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
