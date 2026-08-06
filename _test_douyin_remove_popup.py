"""
用JS移除抖音登录弹窗，然后点击视频
"""
import json, time
from playwright.sync_api import sync_playwright

CDP_PORT = 9333

def main():
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # 用JS移除所有登录相关的弹窗
        result = page.evaluate("""() => {
            const removed = [];
            
            // 移除所有包含login的模态框/弹窗
            const selectors = [
                '[id*="login"]',
                '[class*="login"]',
                '[class*="modal"]',
                '[class*="popup"]',
                '[class*="mask"]',
                '[class*="overlay"]',
            ];
            
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    // 只移除可见的弹窗类元素
                    const style = getComputedStyle(el);
                    if (style.display !== 'none' && style.position === 'fixed') {
                        el.remove();
                        removed.push(sel + ': ' + el.className);
                    }
                }
            }
            
            // 移除 body 的 overflow hidden
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
            
            return { removedCount: removed.length, removed: removed.slice(0, 10) };
        }""")
        
        print(f"移除了 {result['removedCount']} 个弹窗元素")
        if result['removed']:
            for r in result['removed'][:5]:
                print(f"  - {r[:80]}")
        
        time.sleep(2)
        
        # 点击第一个视频卡片
        click_result = page.evaluate("""() => {
            const card = document.querySelector('.discover-video-card-item');
            if (!card) return { error: 'no card found' };
            card.click();
            return { clicked: true };
        }""")
        
        print(f"\n点击结果: {click_result}")
        time.sleep(5)
        
        print(f"当前URL: {page.url}")
        
        # 检查作者信息
        author_info = page.evaluate("""() => {
            const results = [];
            const userLinks = document.querySelectorAll('a[href*="/user/"]');
            for (const a of userLinks) {
                const href = a.href;
                const match = href.match(/\\/user\\/(MS4wLjABAAA[^/?#]+|[^/?#]{20,})/);
                if (!match) continue;
                
                const secUid = match[1];
                if (secUid === 'self' || secUid.includes('self')) continue;
                
                const text = a.textContent.trim();
                if (text && text.length >= 2 && text.length <= 30) {
                    results.push({
                        name: text,
                        sec_uid: secUid,
                        url: href
                    });
                }
            }
            
            const seen = new Set();
            const unique = [];
            for (const r of results) {
                if (!seen.has(r.sec_uid)) {
                    seen.add(r.sec_uid);
                    unique.push(r);
                }
            }
            
            return unique.slice(0, 5);
        }""")
        
        print(f"\n找到作者数: {len(author_info)}")
        for a in author_info:
            print(f"  - {a['name']}: {a['sec_uid']}")
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\douyin_no_popup.png"))
        print("\n已保存截图")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
