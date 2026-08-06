"""
用JS直接点击抖音视频，绕过登录弹窗遮挡
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
        
        # 用JS直接点击第一个视频卡片
        result = page.evaluate("""() => {
            // 找第一个视频卡片
            const card = document.querySelector('.discover-video-card-item');
            if (!card) return { error: 'no card found' };
            
            // 直接用JS点击
            card.click();
            
            return { clicked: true };
        }""")
        
        print(f"点击结果: {result}")
        time.sleep(5)
        
        print(f"当前URL: {page.url}")
        
        # 检查页面中的作者信息
        author_info = page.evaluate("""() => {
            const results = [];
            
            // 找所有用户链接
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
            
            // 去重
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
        
        # 截图
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\douyin_clicked.png"))
        print("\n已保存截图")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
