"""
从抖音 SSR_RENDER_DATA 中提取视频和作者信息
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
        
        # 提取 SSR_RENDER_DATA
        result = page.evaluate("""() => {
            if (!window.SSR_RENDER_DATA) {
                return { error: 'no SSR_RENDER_DATA' };
            }
            
            const data = window.SSR_RENDER_DATA;
            const keys = Object.keys(data);
            
            // 尝试找视频列表
            let videos = [];
            let authors = [];
            
            // 递归搜索 aweme_list 或类似结构
            function findVideos(obj, depth = 0) {
                if (depth > 10 || !obj || typeof obj !== 'object') return;
                
                if (Array.isArray(obj)) {
                    for (const item of obj) {
                        if (item && typeof item === 'object') {
                            // 检查是否是视频对象
                            if (item.aweme_id || item.awemeId || item.vid) {
                                videos.push({
                                    aweme_id: item.aweme_id || item.awemeId,
                                    desc: item.desc || item.desc,
                                    author: item.author ? {
                                        sec_uid: item.author.sec_uid || item.author.secUid,
                                        nickname: item.author.nickname || item.author.nickName,
                                        unique_id: item.author.unique_id || item.author.uniqueId,
                                    } : null
                                });
                            }
                            findVideos(item, depth + 1);
                        }
                    }
                } else {
                    for (const key of Object.keys(obj)) {
                        if (key.includes('aweme') || key.includes('video') || key.includes('feed') || key.includes('list')) {
                            findVideos(obj[key], depth + 1);
                        }
                    }
                }
            }
            
            findVideos(data);
            
            return {
                topLevelKeys: keys.slice(0, 20),
                videoCount: videos.length,
                videos: videos.slice(0, 5),
                dataPreview: JSON.stringify(data).slice(0, 500)
            };
        }""")
        
        if 'error' in result:
            print(f"错误: {result['error']}")
        else:
            print(f"顶层keys: {result['topLevelKeys']}")
            print(f"找到视频数: {result['videoCount']}")
            
            if result['videos']:
                print(f"\n前5个视频:")
                for i, v in enumerate(result['videos']):
                    author = v.get('author', {}) or {}
                    print(f"  #{i+1}: {v.get('desc', '无描述')[:40]}")
                    print(f"    作者: {author.get('nickname', '未知')}")
                    print(f"    sec_uid: {author.get('sec_uid', '无')}")
                    print(f"    aweme_id: {v.get('aweme_id', '无')}")
            
            print(f"\n数据预览: {result['dataPreview'][:300]}...")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
