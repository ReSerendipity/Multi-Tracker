"""
调试快手页面结构
"""
import time
from playwright.sync_api import sync_playwright

CDP_PORT = 9335

def main():
    print("连接快手 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开快手首页...")
        page.goto("https://www.kuaishou.com", wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\kuaishou_home.png"))
        print("已保存截图")
        
        # 检查页面结构
        info = page.evaluate("""() => {
            const allLinks = document.querySelectorAll('a');
            const profileLinks = Array.from(allLinks).filter(a => a.href.includes('/profile/'));
            
            const videoCards = document.querySelectorAll('[class*="video"], [class*="card"], [class*="item"]');
            
            const bodyText = document.body.textContent.slice(0, 3000);
            
            // 找所有包含作者信息的元素
            const authorElements = [];
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const text = el.textContent?.trim() || '';
                if (text.length > 1 && text.length < 20 && el.children.length === 0) {
                    // 可能是用户名
                    const cursor = getComputedStyle(el).cursor;
                    if (cursor === 'pointer') {
                        authorElements.push({
                            tag: el.tagName,
                            class: el.className.slice(0, 50),
                            text: text,
                            cursor: cursor
                        });
                    }
                }
            }
            
            return {
                totalLinks: allLinks.length,
                profileLinks: profileLinks.slice(0, 10).map(a => ({ href: a.href, text: a.textContent.trim().slice(0, 30) })),
                videoCardCount: videoCards.length,
                bodyPreview: bodyText.slice(0, 500),
                authorElements: authorElements.slice(0, 20)
            };
        }""")
        
        print(f"\n总链接数: {info['totalLinks']}")
        print(f"个人主页链接数: {len(info['profileLinks'])}")
        for link in info['profileLinks'][:10]:
            print(f"  - {link['text']}: {link['href'][:80]}")
        
        print(f"\n视频卡片数: {info['videoCardCount']}")
        print(f"\n页面文本预览: {info['bodyPreview'][:400]}...")
        
        print(f"\n可点击的短文本元素（可能是用户名）:")
        for el in info['authorElements'][:15]:
            print(f"  - [{el['tag']}.{el['class'][:30]}] {el['text']}")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
