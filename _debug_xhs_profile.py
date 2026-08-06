"""调试小红书博主主页"""
import time
from playwright.sync_api import sync_playwright

CDP_PORT = 9334
TEST_URL = "https://www.xiaohongshu.com/user/profile/686ab7d6000000000d03d28e"

def main():
    print("连接小红书 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        print("检查登录状态...")
        page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        
        # 检查是否已登录
        login_info = page.evaluate("""() => {
            const cookies = document.cookie;
            const hasLoginCookie = cookies.includes('xsecappid') || cookies.includes('a1') || cookies.includes('webId');
            
            // 找用户头像或用户名
            const userEls = document.querySelectorAll('[class*="user"], [class*="avatar"], [class*="login"]');
            const userTexts = [];
            for (const el of userEls) {
                const text = el.textContent.trim();
                if (text && text.length < 20) {
                    userTexts.push(text);
                }
            }
            
            return {
                hasLoginCookie: hasLoginCookie,
                cookieCount: cookies.split(';').length,
                userElements: userTexts.slice(0, 10),
                url: window.location.href
            };
        }""")
        
        print(f"登录状态: {login_info}")
        
        # 访问博主主页
        print(f"\n访问博主主页: {TEST_URL}")
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\xhs_profile_debug.png"))
        print("已保存截图")
        
        # 检查页面内容
        page_info = page.evaluate("""() => {
            const bodyText = document.body.textContent;
            
            // 找笔记卡片
            const noteCards = document.querySelectorAll('[class*="note"], [class*="card"], [class*="item"], section');
            
            // 找图片/封面
            const images = document.querySelectorAll('img');
            
            // 找链接
            const links = document.querySelectorAll('a');
            const noteLinks = Array.from(links).filter(a => {
                const href = a.href;
                return href.includes('/explore/') || href.includes('/discovery/item/');
            });
            
            return {
                bodyLength: bodyText.length,
                bodyPreview: bodyText.slice(0, 500),
                noteCardCount: noteCards.length,
                imageCount: images.length,
                noteLinkCount: noteLinks.length,
                noteLinkSamples: noteLinks.slice(0, 5).map(a => a.href),
                url: window.location.href
            };
        }""")
        
        print(f"\n页面URL: {page_info['url']}")
        print(f"页面文本长度: {page_info['bodyLength']}")
        print(f"笔记卡片数: {page_info['noteCardCount']}")
        print(f"图片数: {page_info['imageCount']}")
        print(f"笔记链接数: {page_info['noteLinkCount']}")
        print(f"页面文本预览: {page_info['bodyPreview'][:400]}...")
        
        if page_info['noteLinkSamples']:
            print(f"\n笔记链接示例:")
            for link in page_info['noteLinkSamples']:
                print(f"  {link}")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
