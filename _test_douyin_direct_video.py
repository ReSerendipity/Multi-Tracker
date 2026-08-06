"""
从抖音精选页提取视频aweme_id，然后访问视频页获取作者sec_uid
"""
import json, re, time
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
        
        # 提取视频链接
        video_info = page.evaluate("""() => {
            const results = [];
            
            // 找所有视频链接
            const links = document.querySelectorAll('a[href*="/video/"], a[href*="/discover/video/"]');
            for (const a of links) {
                const href = a.href;
                const match = href.match(/\\/video\\/(\\d+)/);
                if (match) {
                    const awemeId = match[1];
                    const text = a.textContent.trim().slice(0, 50);
                    results.push({
                        aweme_id: awemeId,
                        url: href.split('?')[0],
                        text: text
                    });
                }
            }
            
            // 去重
            const seen = new Set();
            const unique = [];
            for (const v of results) {
                if (!seen.has(v.aweme_id)) {
                    seen.add(v.aweme_id);
                    unique.push(v);
                }
            }
            
            return unique.slice(0, 10);
        }""")
        
        print(f"找到 {len(video_info)} 个视频:")
        for i, v in enumerate(video_info[:5]):
            print(f"  #{i+1}: {v['aweme_id']} - {v['text'][:40]}")
        
        # 直接访问第一个视频的URL
        if video_info:
            first_video = video_info[0]
            video_url = first_video['url']
            print(f"\n直接访问视频页: {video_url}")
            
            page.goto(video_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(5)
            
            print(f"当前URL: {page.url}")
            
            # 提取作者信息
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
                
                // 尝试从全局数据中找
                if (window._SSR_HYDRATED_DATA) {
                    try {
                        const data = window._SSR_HYDRATED_DATA;
                        const awemeDetail = data?.awemeDetail || data?.videoDetail;
                        if (awemeDetail) {
                            const author = awemeDetail?.awemeInfo?.author || awemeDetail?.author;
                            if (author) {
                                results.unshift({
                                    name: author.nickname || author.nickName || '',
                                    sec_uid: author.sec_uid || author.secUid || '',
                                    url: author.sec_uid ? 'https://www.douyin.com/user/' + author.sec_uid : ''
                                });
                            }
                        }
                    } catch (e) {}
                }
                
                // 去重
                const seen = new Set();
                const unique = [];
                for (const r of results) {
                    if (r.sec_uid && !seen.has(r.sec_uid)) {
                        seen.add(r.sec_uid);
                        unique.push(r);
                    }
                }
                
                return unique.slice(0, 5);
            }""")
            
            print(f"\n找到作者数: {len(author_info)}")
            for a in author_info:
                print(f"  - {a['name']}: {a['sec_uid']}")
            
            page.screenshot(path=str(r"%USERPROFILE%\Multi-platform information management tool\douyin_video_direct.png"))
            print("\n已保存截图")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
