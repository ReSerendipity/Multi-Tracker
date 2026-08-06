"""
深度调试抖音页面结构
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CDP_PORT = 9333

def main():
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # 深入检查 card 元素
        info = page.evaluate("""() => {
            const cards = document.querySelectorAll('[class*="card"]');
            const results = [];
            
            for (let i = 0; i < Math.min(cards.length, 5); i++) {
                const card = cards[i];
                
                // 获取所有内部元素的文本
                const allText = card.textContent.trim();
                
                // 获取所有链接
                const links = Array.from(card.querySelectorAll('a')).map(a => ({
                    href: a.href,
                    text: a.textContent.trim().slice(0, 50),
                    className: a.className
                }));
                
                // 获取所有有 data-e2e 属性的元素
                const dataE2e = Array.from(card.querySelectorAll('[data-e2e]')).map(el => ({
                    attr: el.getAttribute('data-e2e'),
                    tag: el.tagName,
                    text: el.textContent.trim().slice(0, 50)
                }));
                
                // 获取 card 的 class
                const cardClass = card.className;
                
                // 获取内部所有 span/div 中可能包含用户名的
                const textElements = [];
                const spans = card.querySelectorAll('span, div');
                for (const el of spans) {
                    const text = el.textContent.trim();
                    if (text && text.length > 1 && text.length < 30) {
                        // 检查是否像用户名
                        if (!text.includes('播放') && !text.includes('点赞') && !text.includes('评论') && !text.includes('收藏') && !text.includes('分享')) {
                            textElements.push({
                                tag: el.tagName,
                                class: el.className,
                                text: text
                            });
                        }
                    }
                }
                
                results.push({
                    cardClass: cardClass,
                    textLength: allText.length,
                    textPreview: allText.slice(0, 300),
                    links: links,
                    dataE2e: dataE2e,
                    textElements: textElements.slice(0, 10)
                });
            }
            
            return results;
        }""")
        
        for i, card in enumerate(info):
            print(f"\n=== 卡片 #{i+1} ===")
            print(f"类名: {card['cardClass'][:100]}")
            print(f"文本长度: {card['textLength']}")
            print(f"文本预览: {card['textPreview'][:200]}...")
            
            if card['links']:
                print(f"\n链接:")
                for link in card['links'][:5]:
                    print(f"  - [{link['className'][:30]}] {link['text']}: {link['href'][:80]}")
            
            if card['dataE2e']:
                print(f"\ndata-e2e 元素:")
                for el in card['dataE2e'][:5]:
                    print(f"  - {el['attr']}: {el['text']}")
            
            if card['textElements']:
                print(f"\n文本元素:")
                for el in card['textElements'][:8]:
                    print(f"  - [{el['tag']}.{el['class'][:30]}] {el['text']}")
        
        # 另外，尝试直接访问一个视频页面来获取博主信息
        print("\n\n=== 尝试获取当前播放视频的作者信息 ===")
        
        author_info = page.evaluate("""() => {
            // 尝试多种选择器找作者信息
            const selectors = [
                '[data-e2e="feed-author-name"]',
                '[data-e2e="author-name"]',
                '.author-name',
                '.user-name',
                '.nickname',
                '[class*="author-name"]',
                '[class*="userName"]',
                '[class*="nick-name"]',
            ];
            
            const results = {};
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    results[sel] = Array.from(els).map(el => ({
                        text: el.textContent.trim().slice(0, 50),
                        href: el.href || el.closest('a')?.href || ''
                    }));
                }
            }
            
            return results;
        }""")
        
        for sel, data in author_info.items():
            print(f"\n{sel}:")
            for item in data:
                print(f"  - {item['text']} | {item['href'][:80]}")
        
        page.close()
        browser.close()

if __name__ == "__main__":
    main()
