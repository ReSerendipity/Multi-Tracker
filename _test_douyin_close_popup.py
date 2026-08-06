"""
测试：关闭抖音登录弹窗后再点击作者
"""
import re
import time
from playwright.sync_api import sync_playwright

CDP_PORT = 9333

def close_login_popup(page):
    """尝试各种方式关闭登录弹窗"""
    try:
        # 方法1: 找关闭按钮 X
        close_selectors = [
            '.login-close',
            '[class*="login"] [class*="close"]',
            '.dy-modal .dy-icon-close',
            '[data-e2e="login-close"]',
            '.loginV2 [class*="close"]',
        ]
        
        for sel in close_selectors:
            btns = page.query_selector_all(sel)
            for btn in btns:
                try:
                    if btn.is_visible():
                        btn.click(force=True)
                        time.sleep(1)
                        print(f"  用 {sel} 关闭了弹窗")
                        return True
                except:
                    continue
        
        # 方法2: 点击 ESC 键
        page.keyboard.press("Escape")
        time.sleep(1)
        
        # 方法3: 点击遮罩层外部
        overlays = page.query_selector_all('[class*="mask"], [class*="overlay"], [class*="modal-mask"]')
        for overlay in overlays:
            try:
                if overlay.is_visible():
                    # 点击左上角
                    box = overlay.bounding_box()
                    if box:
                        page.mouse.click(box["x"] + 10, box["y"] + 10)
                        time.sleep(1)
            except:
                continue
        
        # 检查弹窗是否还在
        has_popup = page.evaluate("""() => {
            const loginEl = document.querySelector('.loginV2, [class*="login-panel"]');
            if (!loginEl) return false;
            const style = getComputedStyle(loginEl);
            return style.display !== 'none' && style.visibility !== 'hidden';
        }""")
        
        return not has_popup
    except Exception as e:
        print(f"  关闭弹窗出错: {e}")
        return False

def main():
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        
        print("尝试关闭登录弹窗...")
        close_login_popup(page)
        close_login_popup(page)  # 再试一次
        
        # 截图看看状态
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\douyin_after_close.png"))
        print("已保存截图")
        
        # 再次尝试点击作者
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
                        beforeUrl: beforeUrl
                    };
                }
            }
            return { clicked: false };
        }""")
        
        print(f"点击结果: {result.get('clicked', False)}")
        
        if result.get("clicked"):
            time.sleep(5)
            print(f"当前URL: {page.url}")
            
            if "/user/" in page.url:
                match = re.search(r"/user/(MS4wLjABAAA[^/?#]+|[^/?#]{20,})", page.url)
                if match:
                    print(f"找到 sec_uid: {match.group(1)}")
        
        browser.close()
        print("完成!")

if __name__ == "__main__":
    main()
