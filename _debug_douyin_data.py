"""
从抖音精选页全局JS数据中提取视频和作者信息
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
        
        # 尝试从全局数据中提取视频信息
        result = page.evaluate("""() => {
            const results = [];
            
            // 方法1: 检查 _SSR_HYDRATED_DATA
            if (window._SSR_HYDRATED_DATA) {
                try {
                    const data = window._SSR_HYDRATED_DATA;
                    // 尝试找精选页数据
                    const feed = data?.discoverFeed || data?.feed || data?.recommend;
                    if (feed) {
                        return { source: '_SSR_HYDRATED_DATA', data: JSON.stringify(feed).slice(0, 1000) };
                    }
                    return { source: '_SSR_HYDRATED_DATA', keys: Object.keys(data).slice(0, 20) };
                } catch (e) {
                    return { source: '_SSR_HYDRATED_DATA', error: e.message };
                }
            }
            
            // 方法2: 找所有包含 aweme 或 sec_uid 的全局变量
            const windowKeys = Object.keys(window).filter(k => 
                k.includes('aweme') || k.includes('feed') || k.includes('SSR') || k.includes('HYDRATE') || k.includes('REACT')
            );
            
            return { source: 'window_keys', keys: windowKeys.slice(0, 30) };
        }""")
        
        print(f"数据来源: {result.get('source')}")
        if 'keys' in result:
            print(f"相关全局变量: {result['keys']}")
        if 'data' in result:
            print(f"数据预览: {result['data'][:500]}")
        if 'error' in result:
            print(f"错误: {result['error']}")
        
        # 方法3: 从网络请求中获取（通过拦截）太复杂
        # 方法4: 从页面元素的 __reactProps 或类似属性中获取
        react_result = page.evaluate("""() => {
            // 找视频卡片的react属性
            const cards = document.querySelectorAll('.discover-video-card-item');
            if (cards.length === 0) return { error: 'no cards found' };
            
            const firstCard = cards[0];
            const props = {};
            
            // 遍历所有属性名
            for (const key of Object.keys(firstCard)) {
                if (key.startsWith('__') || key.includes('react') || key.includes('fiber')) {
                    props[key] = typeof firstCard[key];
                }
            }
            
            // 尝试获取 __reactProps 或类似数据
            let reactData = null;
            for (const key of Object.keys(firstCard)) {
                if (key.startsWith('__reactProps')) {
                    try {
                        const data = firstCard[key];
                        return { 
                            reactPropsKey: key,
                            propsKeys: Object.keys(data || {}).slice(0, 20),
                            dataPreview: JSON.stringify(data).slice(0, 500)
                        };
                    } catch (e) {}
                }
            }
            
            return { cardCount: cards.length, props: props };
        }""")
        
        print(f"\nReact属性分析:")
        print(json.dumps(react_result, ensure_ascii=False, indent=2)[:1000])
        
        # 方法5: 直接从页面中的script标签找数据
        script_result = page.evaluate("""() => {
            const scripts = document.querySelectorAll('script');
            const results = [];
            
            for (const script of scripts) {
                const text = script.textContent || '';
                if (text.includes('sec_uid') || text.includes('aweme_id') || text.includes('awemeId')) {
                    results.push({
                        length: text.length,
                        preview: text.slice(0, 200)
                    });
                }
            }
            
            return { scriptCount: scripts.length, dataScripts: results.slice(0, 5) };
        }""")
        
        print(f"\nScript标签分析:")
        print(f"  总script数: {script_result['scriptCount']}")
        print(f"  含数据的script数: {len(script_result.get('dataScripts', []))}")
        for i, s in enumerate(script_result.get('dataScripts', [])[:3]):
            print(f"  Script #{i+1} (长度: {s['length']}): {s['preview'][:100]}...")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
