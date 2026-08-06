"""
测试：通过抖音搜索页面查找博主
"""
import re
import time
import urllib.parse
from playwright.sync_api import sync_playwright

CDP_PORT = 9333

def main():
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        # 先从精选页提取几个作者名
        print("从精选页提取作者名...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        
        author_names = page.evaluate("""() => {
            const names = new Set();
            const cards = document.querySelectorAll('.discover-video-card-item');
            for (const card of cards) {
                const text = card.textContent || '';
                const regex = /@([^·\\n\\r@#]{2,30}?)(?:\\s*·|\\s|$)/g;
                let match;
                while ((match = regex.exec(text)) !== null) {
                    let name = match[1].trim();
                    name = name.replace(/\\u00a0/g, '').trim();
                    if (name && name.length >= 2 && name.length <= 30) {
                        names.add(name);
                    }
                }
            }
            return Array.from(names).slice(0, 3);
        }""")
        
        print(f"找到 {len(author_names)} 个作者: {author_names}")
        
        # 尝试搜索第一个作者
        if author_names:
            search_name = author_names[0]
            print(f"\n搜索: {search_name}")
            
            search_url = f"https://www.douyin.com/search/{urllib.parse.quote(search_name)}?type=user"
            page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(5)
            
            # 截图
            page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\douyin_search.png"))
            print("已保存搜索结果截图")
            
            # 提取搜索结果中的用户
            results = page.evaluate("""() => {
                const users = [];
                
                // 找用户链接
                const userLinks = document.querySelectorAll('a[href*="/user/"]');
                for (const a of userLinks) {
                    const href = a.href;
                    const match = href.match(/\\/user\\/(MS4wLjABAAA[^/?#]+|[^/?#]{20,})/);
                    if (!match) continue;
                    
                    const secUid = match[1];
                    if (secUid === 'self' || secUid.includes('self')) continue;
                    
                    // 获取用户名
                    let name = '';
                    const nameEl = a.querySelector('[class*="name"], [class*="title"], [class*="nickname"]');
                    if (nameEl) {
                        name = nameEl.textContent.trim();
                    }
                    if (!name) {
                        name = a.textContent.trim().slice(0, 30);
                    }
                    
                    if (name && name.length >= 2) {
                        users.push({
                            name: name,
                            sec_uid: secUid,
                            url: href
                        });
                    }
                }
                
                // 去重
                const seen = new Set();
                const unique = [];
                for (const u of users) {
                    if (!seen.has(u.sec_uid)) {
                        seen.add(u.sec_uid);
                        unique.push(u);
                    }
                }
                
                return unique.slice(0, 5);
            }""")
            
            print(f"\n搜索结果用户数: {len(results)}")
            for u in results:
                print(f"  - {u['name']}: {u['url']}")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
