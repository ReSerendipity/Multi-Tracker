"""测试小红书博主主页访问"""
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
        
        print("先浏览首页...")
        page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)
        
        # 滚动一下
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(2)
        
        print(f"访问博主主页: {TEST_URL}")
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(5)
        
        print(f"当前URL: {page.url}")
        
        if "login" in page.url.lower():
            print("⚠️ 被重定向到登录页，尝试返回并点击笔记进入...")
            
            # 返回发现页
            page.go_back(wait_until="domcontentloaded")
            time.sleep(3)
            
            # 点击第一个笔记
            result = page.evaluate("""() => {
                const noteLinks = document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]');
                if (noteLinks.length > 0) {
                    const firstNote = noteLinks[0];
                    const href = firstNote.href;
                    setTimeout(() => firstNote.click(), 500);
                    return { found: true, href: href };
                }
                return { found: false };
            }""")
            
            print(f"点击第一个笔记: {result}")
            time.sleep(5)
            
            print(f"笔记页URL: {page.url}")
            
            # 从笔记页点击作者头像
            author_info = page.evaluate("""() => {
                const userLinks = document.querySelectorAll('a[href*="/user/profile/"]');
                if (userLinks.length > 0) {
                    return {
                        found: true,
                        authorName: userLinks[0].textContent.trim().slice(0, 30),
                        authorLink: userLinks[0].href
                    };
                }
                return { found: false };
            }""")
            
            print(f"笔记页作者信息: {author_info}")
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\xhs_profile_test2.png"))
        print("已保存截图")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
