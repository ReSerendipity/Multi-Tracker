"""
测试点击抖音作者名获取主页链接
"""
import re
import time
from playwright.sync_api import sync_playwright

CDP_PORT = 9333

def main():
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        
        # 使用 evaluate 找到并点击第一个作者元素
        result = page.evaluate("""() => {
            const card = document.querySelector('.discover-video-card-item');
            if (!card) return { error: 'no card' };
            
            const allEls = card.querySelectorAll('*');
            for (const el of allEls) {
                const text = el.textContent?.trim() || '';
                if (text.startsWith('@') && text.length < 30 && getComputedStyle(el).cursor === 'pointer') {
                    const beforeUrl = window.location.href;
                    el.click();
                    return { 
                        clicked: true, 
                        text: text,
                        tag: el.tagName,
                        class: el.className.slice(0, 50),
                        beforeUrl: beforeUrl
                    };
                }
            }
            return { clicked: false, cardText: card.textContent.slice(0, 100) };
        }""")
        
        print(f"点击结果: {result}")
        
        if result.get("clicked"):
            time.sleep(5)
            current_url = page.url
            print(f"当前URL: {current_url}")
            
            # 检查是否有用户路径
            if "/user/" in current_url:
                match = re.search(r"/user/(MS4wLjABAAA[^/?#]+|[^/?#]{20,})", current_url)
                if match:
                    print(f"找到 sec_uid: {match.group(1)}")
            
            # 检查是否有登录弹窗
            has_popup = page.evaluate("""() => {
                const popups = document.querySelectorAll('[class*="login"], [class*="modal"], [id*="login"]');
                const visiblePopups = [];
                for (const popup of popups) {
                    const style = getComputedStyle(popup);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        visiblePopups.push(popup.className.slice(0, 50));
                    }
                }
                return { count: visiblePopups.length, classes: visiblePopups.slice(0, 5) };
            }""")
            print(f"登录弹窗: {has_popup}")
        
        browser.close()
        print("完成!")

if __name__ == "__main__":
    main()
