"""调试快手博主主页"""
import time
from playwright.sync_api import sync_playwright

CDP_PORT = 9335
TEST_URL = "https://www.kuaishou.com/profile/3x56cmwuytsdqkk"

def main():
    print("连接快手 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        print(f"访问博主主页: {TEST_URL}")
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)
        
        print(f"当前URL: {page.url}")
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\ks_profile_debug.png"))
        print("已保存截图")
        
        # 检查页面内容
        page_info = page.evaluate("""() => {
            const bodyText = document.body.textContent;
            
            // 找视频
            const videos = document.querySelectorAll('video');
            
            // 找视频卡片
            const videoCards = document.querySelectorAll('[class*="video"], [class*="item"], [class*="card"]');
            
            // 找作品数量等信息
            const profileInfo = {
                hasVideo: videos.length > 0,
                videoCount: videos.length,
                videoCardCount: videoCards.length,
                bodyLength: bodyText.length,
            };
            
            // 检查是否有登录提示
            if (bodyText.includes('登录') && bodyText.length < 3000) {
                profileInfo.isLoginPage = true;
            }
            
            return {
                url: window.location.href,
                bodyPreview: bodyText.slice(0, 600),
                ...profileInfo
            };
        }""")
        
        print(f"\n页面URL: {page_info['url']}")
        print(f"页面文本长度: {page_info['bodyLength']}")
        print(f"视频数: {page_info.get('videoCount', 0)}")
        print(f"视频卡片数: {page_info.get('videoCardCount', 0)}")
        print(f"是否登录页: {page_info.get('isLoginPage', False)}")
        print(f"页面文本预览: {page_info['bodyPreview'][:500]}...")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
