"""
调试：从抖音视频卡片中提取 @ 用户名，并尝试点击获取详情
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
        
        # 提取所有 @用户名
        info = page.evaluate("""() => {
            const cards = document.querySelectorAll('.discover-video-card-item');
            const results = [];
            
            for (const card of cards) {
                const text = card.textContent || '';
                // 匹配 @用户名 模式
                const atMatches = text.match(/@([^·\\n\\r@#]{2,30})/g);
                if (atMatches) {
                    results.push({
                        cardText: text.slice(0, 100),
                        atNames: atMatches.slice(0, 3)
                    });
                }
                
                // 同时检查有没有可点击的作者元素
                const clickableAuthors = [];
                const allEls = card.querySelectorAll('*');
                for (const el of allEls) {
                    const elText = el.textContent?.trim() || '';
                    if (elText.startsWith('@') && elText.length < 30) {
                        clickableAuthors.push({
                            tag: el.tagName,
                            class: el.className,
                            text: elText,
                            onclick: el.onclick ? 'has-onclick' : 'no-onclick',
                            cursor: getComputedStyle(el).cursor
                        });
                    }
                }
                
                if (clickableAuthors.length > 0 && results.length > 0) {
                    results[results.length - 1].clickableAuthors = clickableAuthors;
                }
            }
            
            return results.slice(0, 10);
        }""")
        
        print(f"找到 {len(info)} 个包含 @用户名 的卡片:")
        for i, card in enumerate(info):
            print(f"\n卡片 #{i+1}:")
            print(f"  文本: {card['cardText'][:80]}...")
            print(f"  @用户名: {card.get('atNames', [])}")
            if card.get('clickableAuthors'):
                print(f"  可点击作者元素:")
                for author in card['clickableAuthors'][:3]:
                    print(f"    - [{author['tag']}.{author['class'][:30]}] {author['text']} (cursor: {author['cursor']})")
        
        # 尝试点击第一个视频卡片，看看视频播放页的作者信息
        if info:
            print("\n\n=== 点击第一个视频，查看播放页作者信息 ===")
            
            # 点击第一个视频卡片
            first_card = page.query_selector('.discover-video-card-item')
            if first_card:
                first_card.click()
                page.wait_for_timeout(5000)
                
                # 截图
                page.screenshot(path=str(ROOT / "douyin_video_page.png"), full_page=False)
                print("已保存截图: douyin_video_page.png")
                
                # 提取播放页的作者信息
                author_info = page.evaluate("""() => {
                    const results = {};
                    
                    // 找所有用户链接
                    const userLinks = document.querySelectorAll('a[href*="/user/"]');
                    results.userLinks = Array.from(userLinks).map(a => ({
                        href: a.href,
                        text: a.textContent.trim().slice(0, 50),
                        class: a.className
                    })).slice(0, 10);
                    
                    // 找作者名称
                    const authorSelectors = [
                        '[data-e2e="feed-author-name"]',
                        '[data-e2e="author-name"]',
                        '.author-name',
                        '.user-name',
                        '[class*="author-name"]',
                        '[class*="userName"]',
                    ];
                    
                    for (const sel of authorSelectors) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            results[sel] = Array.from(els).map(el => el.textContent.trim().slice(0, 50));
                        }
                    }
                    
                    // 获取页面上所有包含 "的抖音" 的文本
                    const allText = document.body.textContent;
                    const douyinMatch = allText.match(/(.{1,30})的抖音/);
                    if (douyinMatch) {
                        results.pageTitleAuthor = douyinMatch[1].trim();
                    }
                    
                    return results;
                }""")
                
                print(f"\n用户链接:")
                for link in author_info.get('userLinks', []):
                    if 'self' not in link['href']:
                        print(f"  - {link['text']}: {link['href']}")
                
                for key, value in author_info.items():
                    if key != 'userLinks' and key != 'pageTitleAuthor':
                        print(f"\n{key}: {value}")
                
                if author_info.get('pageTitleAuthor'):
                    print(f"\n页面标题作者: {author_info['pageTitleAuthor']}")
        
        page.close()
        browser.close()

if __name__ == "__main__":
    main()
