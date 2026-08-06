"""详细调试快手博主主页"""
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
        page.goto(TEST_URL, wait_until="networkidle", timeout=30000)
        time.sleep(5)
        
        # 滚动加载
        print("滚动加载内容...")
        for i in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)
        
        page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\ks_profile_debug2.png"))
        print("已保存截图")
        
        # 详细检查页面结构
        page_info = page.evaluate("""() => {
            const results = {};
            
            // 找所有链接
            const allLinks = document.querySelectorAll('a');
            results.totalLinks = allLinks.length;
            
            // 找视频链接
            const videoLinks = Array.from(allLinks).filter(a => {
                const href = a.href;
                return href.includes('/short-video/') || href.includes('/video/') || href.includes('photoId');
            });
            results.videoLinks = videoLinks.slice(0, 10).map(a => ({
                href: a.href.slice(0, 100),
                text: a.textContent.trim().slice(0, 50)
            }));
            
            // 找视频元素
            results.videoCount = document.querySelectorAll('video').length;
            
            // 找作品/视频相关的类名
            const allElements = document.querySelectorAll('*');
            const videoClasses = new Set();
            for (const el of allElements) {
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.split(' ');
                    for (const c of classes) {
                        if (c.match(/video|item|card|work|photo|feed/i)) {
                            videoClasses.add(c);
                        }
                    }
                }
            }
            results.videoClasses = Array.from(videoClasses).slice(0, 30);
            
            // 检查页面可见文本
            const visibleText = document.body.innerText;
            results.visibleTextLength = visibleText.length;
            results.visibleTextPreview = visibleText.slice(0, 500);
            
            // 检查作品数量
            const workMatch = visibleText.match(/作品[：: ]*(\\d+)/);
            if (workMatch) {
                results.workCount = workMatch[1];
            }
            
            return results;
        }""")
        
        print(f"\n总链接数: {page_info['totalLinks']}")
        print(f"视频元素数: {page_info['videoCount']}")
        print(f"视频链接数: {len(page_info['videoLinks'])}")
        print(f"可见文本长度: {page_info['visibleTextLength']}")
        
        if page_info.get('workCount'):
            print(f"作品数量: {page_info['workCount']}")
        
        if page_info['videoLinks']:
            print(f"\n视频链接示例:")
            for link in page_info['videoLinks'][:5]:
                print(f"  - {link['text']}: {link['href']}")
        
        print(f"\n视频相关类名:")
        for cls in page_info['videoClasses'][:15]:
            print(f"  - {cls}")
        
        print(f"\n可见文本预览: {page_info['visibleTextPreview'][:400]}...")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
