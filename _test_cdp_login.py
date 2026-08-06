"""
测试 CDP 连接和 B 站登录态
"""
import json
import urllib.request
from playwright.sync_api import sync_playwright


def test_cdp():
    # 测试 CDP 连接
    resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version")
    info = json.loads(resp.read())
    print("CDP 连接成功!")
    print(f"  浏览器: {info.get('Browser', '?')}")
    
    # 通过 CDP 检查 B 站登录态
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        # 新开一个页面访问 B 站 nav 接口
        page = context.new_page()
        try:
            page.goto("https://api.bilibili.com/x/web-interface/nav", wait_until="domcontentloaded", timeout=30000)
            content = page.evaluate("() => document.body.innerText")
            data = json.loads(content)
            
            if data.get("code") == 0:
                user = data["data"]
                print(f"\nB站登录态: ✅ 已登录")
                print(f"  用户名: {user.get('uname', '?')}")
                print(f"  UID: {user.get('mid', '?')}")
                print(f"  等级: Lv{user.get('level_info', {}).get('current_level', '?')}")
                return True
            else:
                print(f"\nB站登录态: ❌ 未登录")
                print(f"  错误: {data.get('message', '?')}")
                return False
        finally:
            page.close()
            browser.close()


if __name__ == "__main__":
    test_cdp()
