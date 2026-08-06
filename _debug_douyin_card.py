"""
深入检查抖音视频卡片结构，找aweme_id
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
        
        # 深入检查第一个视频卡片
        result = page.evaluate("""() => {
            const card = document.querySelector('.discover-video-card-item');
            if (!card) return { error: 'no card' };
            
            const info = {};
            
            // 获取所有data属性
            const dataAttrs = {};
            for (const attr of card.attributes) {
                if (attr.name.startsWith('data-')) {
                    dataAttrs[attr.name] = attr.value;
                }
            }
            info.dataAttrs = dataAttrs;
            
            // 获取卡片的innerHTML
            info.innerHTML = card.innerHTML.slice(0, 2000);
            
            // 找所有包含数字的属性（可能是aweme_id）
            const allEls = card.querySelectorAll('*');
            const idAttrs = [];
            for (const el of allEls) {
                for (const attr of el.attributes) {
                    const val = attr.value;
                    if (/\\d{15,25}/.test(val)) {
                        idAttrs.push({
                            tag: el.tagName,
                            attr: attr.name,
                            value: val.slice(0, 50)
                        });
                    }
                }
                // 检查元素的id
                if (el.id && /\\d{15,25}/.test(el.id)) {
                    idAttrs.push({ tag: el.tagName, attr: 'id', value: el.id });
                }
            }
            
            info.idAttrs = idAttrs.slice(0, 20);
            
            // 检查内部所有链接
            const links = Array.from(card.querySelectorAll('a')).map(a => ({
                href: a.href.slice(0, 100),
                text: a.textContent.trim().slice(0, 30)
            }));
            info.links = links.slice(0, 10);
            
            // 从card的react fiber中找数据
            for (const key of Object.keys(card)) {
                if (key.startsWith('__reactFiber') || key.startsWith('__reactProps')) {
                    try {
                        const fiber = card[key];
                        info[key] = typeof fiber;
                        // 尝试找 memoizedProps / stateNode
                        if (fiber?.memoizedProps) {
                            info.reactPropsKeys = Object.keys(fiber.memoizedProps).slice(0, 20);
                            // 看看有没有 video / aweme 数据
                            const props = fiber.memoizedProps;
                            for (const k of Object.keys(props)) {
                                if (k.includes('video') || k.includes('aweme') || k.includes('data')) {
                                    info['prop_' + k] = typeof props[k];
                                }
                            }
                        }
                    } catch (e) {}
                    break;
                }
            }
            
            return info;
        }""")
        
        if 'error' in result:
            print(f"错误: {result['error']}")
        else:
            print(f"data属性: {json.dumps(result.get('dataAttrs', {}), ensure_ascii=False)}")
            print(f"\n链接数: {len(result.get('links', []))}")
            for link in result.get('links', [])[:8]:
                print(f"  - {link['text']}: {link['href']}")
            
            print(f"\n含长数字的属性: {len(result.get('idAttrs', []))}")
            for attr in result.get('idAttrs', [])[:10]:
                print(f"  - [{attr['tag']}.{attr['attr']}] {attr['value']}")
            
            print(f"\nReact属性:")
            for key in result:
                if key.startswith('__react') or key.startswith('prop_') or key == 'reactPropsKeys':
                    print(f"  {key}: {result[key]}")
            
            print(f"\nHTML预览: {result.get('innerHTML', '')[:500]}...")
        
        browser.close()
        print("\n完成!")

if __name__ == "__main__":
    main()
