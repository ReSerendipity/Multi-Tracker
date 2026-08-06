"""
调试抖音页面结构，查看博主信息如何组织
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CDP_PORT = 9333

def main():
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # 截图保存
        page.screenshot(path=str(ROOT / "douyin_debug_feed.png"), full_page=False)
        print("已保存截图: douyin_debug_feed.png")
        
        # 检查页面上的链接
        info = page.evaluate("""() => {
            const allLinks = Array.from(document.querySelectorAll('a'));
            const userLinks = allLinks.filter(a => a.href.includes('/user/'));
            const hrefs = userLinks.map(a => a.href).slice(0, 20);
            
            // 检查页面上有哪些类名包含 author/user/name
            const allElements = document.querySelectorAll('*');
            const authorClasses = new Set();
            for (const el of allElements) {
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.split(' ');
                    for (const c of classes) {
                        if (c.match(/author|user|name|nick/i)) {
                            authorClasses.add(c);
                        }
                    }
                }
            }
            
            return {
                totalLinks: allLinks.length,
                userLinksCount: userLinks.length,
                userLinkHrefs: hrefs,
                authorRelatedClasses: Array.from(authorClasses).slice(0, 30),
            };
        }""")
        
        print(f"\n页面链接总数: {info['totalLinks']}")
        print(f"包含 /user/ 的链接数: {info['userLinksCount']}")
        print(f"\n用户链接示例:")
        for href in info['userLinkHrefs'][:10]:
            print(f"  {href}")
        
        print(f"\n作者相关类名:")
        for cls in info['authorRelatedClasses']:
            print(f"  {cls}")
        
        # 更深入地检查视频卡片
        video_info = page.evaluate("""() => {
            // 查找视频相关元素
            const selectors = [
                '[data-e2e="feed-active-video"]',
                '[class*="video-item"]',
                '[class*="feed-item"]',
                '[class*="card"]',
            ];
            
            const results = {};
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    // 取第一个元素的HTML结构概要
                    const first = els[0];
                    const linksInFirst = Array.from(first.querySelectorAll('a')).map(a => ({
                        href: a.href,
                        text: a.textContent.trim().slice(0, 50)
                    })).slice(0, 10);
                    
                    results[sel] = {
                        count: els.length,
                        firstElementLinks: linksInFirst,
                        firstElementText: first.textContent.trim().slice(0, 200),
                    };
                }
            }
            
            return results;
        }""")
        
        print(f"\n视频卡片结构:")
        for sel, data in video_info.items():
            print(f"\n  选择器: {sel} (数量: {data['count']})")
            print(f"  文本摘要: {data['firstElementText'][:100]}...")
            if data['firstElementLinks']:
                print(f"  内部链接:")
                for link in data['firstElementLinks'][:5]:
                    print(f"    - {link['text']}: {link['href'][:80]}")
        
        page.close()
        browser.close()

if __name__ == "__main__":
    main()
