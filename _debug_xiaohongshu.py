"""
调试小红书页面结构
"""
import time
from playwright.sync_api import sync_playwright

CDP_PORT = 9334

def main():
    print("连接小红书 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开小红书发现页...")
        page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\xiaohongshu_explore.png"))
        print("已保存截图")
        
        # 检查页面结构
        info = page.evaluate("""() => {
            const allLinks = document.querySelectorAll('a');
            const userLinks = Array.from(allLinks).filter(a => a.href.includes('/user/profile/'));
            
            const noteCards = document.querySelectorAll('[class*="note"], [class*="card"], [class*="item"]');
            
            const bodyText = document.body.textContent.slice(0, 3000);
            
            return {
                totalLinks: allLinks.length,
                userLinks: userLinks.slice(0, 10).map(a => ({ href: a.href, text: a.textContent.trim().slice(0, 30) })),
                noteCardCount: noteCards.length,
                bodyPreview: bodyText.slice(0, 500),
                url: window.location.href
            };
        }""")
        
        print(f"\n当前URL: {info['url']}")
        print(f"总链接数: {info['totalLinks']}")
        print(f"用户主页链接数: {len(info['userLinks'])}")
        for link in info['userLinks'][:10]:
            print(f"  - {link['text']}: {link['href'][:80]}")
        
        print(f"\n笔记卡片数: {info['noteCardCount']}")
        print(f"\n页面文本预览: {info['bodyPreview'][:400]}...")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
