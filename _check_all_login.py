"""检查三个平台的登录状态"""
import time
from playwright.sync_api import sync_playwright

platforms = [
    {"name": "抖音", "port": 9333, "test_url": "https://www.douyin.com/jingxuan", "login_indicator": "@"},
    {"name": "小红书", "port": 9334, "test_url": "https://www.xiaohongshu.com/explore", "login_indicator": "登录"},
    {"name": "快手", "port": 9335, "test_url": "https://www.kuaishou.com", "login_indicator": "登录"},
]

def main():
    for plat in platforms:
        print(f"\n{'='*50}")
        print(f"检查 {plat['name']} 登录状态 (端口 {plat['port']})")
        print(f"{'='*50}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{plat['port']}")
                context = browser.contexts[0]
                page = context.new_page()
                
                page.goto(plat['test_url'], wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)
                
                # 检查页面内容
                body_text = page.evaluate("() => document.body.textContent")
                has_login_text = "登录" in body_text and len(body_text) < 5000  # 登录页通常内容少
                
                # 检查cookie
                cookies = context.cookies()
                cookie_count = len(cookies)
                
                # 检查URL
                current_url = page.url
                
                print(f"当前URL: {current_url}")
                print(f"Cookie数量: {cookie_count}")
                print(f"页面文本长度: {len(body_text)}")
                
                # 判断登录状态
                is_login_page = "login" in current_url.lower()
                print(f"是否在登录页: {is_login_page}")
                
                if plat['name'] == "抖音":
                    # 抖音：能看到视频就是登录了
                    has_videos = "discover-video-card-item" in body_text or "video" in body_text.lower()
                    print(f"是否有视频内容: {has_videos}")
                    print(f"登录状态: {'⚠️ 未完全登录(有弹窗)' if has_videos else '❌ 未登录'}")
                elif plat['name'] == "小红书":
                    print(f"登录状态: {'❌ 未登录' if is_login_page else '✅ 已登录'}")
                elif plat['name'] == "快手":
                    has_profile = "profile" in body_text.lower()
                    print(f"是否有博主信息: {has_profile}")
                    print(f"登录状态: {'❓ 待确认' if is_login_page else '✅ 可能已登录'}")
                
                page.close()
                browser.close()
        except Exception as e:
            print(f"连接失败: {e}")

if __name__ == "__main__":
    main()
