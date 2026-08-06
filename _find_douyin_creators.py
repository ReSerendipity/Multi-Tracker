"""
通过抖音精选页面找博主：提取@用户名，尽量获取主页链接
"""
import json, sys, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from download_bili_following_latest import load_config, run_lark

CDP_PORT = 9333

def extract_creators_from_feed(page, target_count=8):
    """从推荐流中提取博主信息"""
    creators = {}  # key: name
    scroll_attempts = 0
    max_attempts = 10
    
    while len(creators) < target_count and scroll_attempts < max_attempts:
        scroll_attempts += 1
        
        # 提取当前页面的作者名
        new_names = page.evaluate("""() => {
            const names = [];
            const cards = document.querySelectorAll('.discover-video-card-item');
            
            for (const card of cards) {
                const text = card.textContent || '';
                const regex = /@([^·\\n\\r@#]{2,30}?)(?:\\s*·|\\s|$)/g;
                let match;
                while ((match = regex.exec(text)) !== null) {
                    let name = match[1].trim();
                    name = name.replace(/\\u00a0/g, '').trim();
                    if (name && name.length >= 2 && name.length <= 30 && !names.includes(name)) {
                        names.push(name);
                    }
                }
            }
            
            return names;
        }""")
        
        print(f"  第{scroll_attempts}次滚动，找到 {len(new_names)} 个作者名")
        
        for name in new_names:
            if name not in creators and len(creators) < target_count:
                creators[name] = {
                    'name': name,
                    'sec_uid': '',
                    'url': '',
                }
        
        # 滚动加载更多
        if len(creators) < target_count:
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(2000)
    
    return list(creators.values())[:target_count]


def try_get_sec_uids(page, creators):
    """尝试通过搜索获取 sec_uid（尽量获取，不保证全部成功）"""
    success_count = 0
    
    for creator in creators:
        if creator.get('sec_uid'):
            continue
        
        name = creator['name']
        try:
            # 访问搜索页
            search_url = f"https://www.douyin.com/search/{name}?type=user"
            page.goto(search_url, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(3000)
            
            # 提取第一个用户
            result = page.evaluate("""() => {
                const userLinks = document.querySelectorAll('a[href*="/user/"]');
                for (const a of userLinks) {
                    const href = a.href;
                    const match = href.match(/\\/user\\/(MS4wLjABAAA[^/?#]+|[^/?#]{20,})/);
                    if (!match) continue;
                    
                    const secUid = match[1];
                    if (secUid === 'self' || secUid.includes('self')) continue;
                    
                    return { sec_uid: secUid, url: href };
                }
                return null;
            }""")
            
            if result:
                creator['sec_uid'] = result['sec_uid']
                creator['url'] = result['url']
                success_count += 1
                print(f"  ✅ {name}: 获取到 sec_uid")
            else:
                print(f"  ⚠️  {name}: 未找到 sec_uid")
                
        except Exception as e:
            print(f"  ❌ {name}: 搜索出错 - {e}")
    
    return success_count


def add_creator_to_feishu(config, creator):
    """添加博主到飞书表"""
    table_id = config["tables"]["creators"]["table_id"]
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    fields = {
        "博主名称": creator['name'],
        "平台": ["抖音"],
        "抖音持续跟踪": True,
    }
    
    if creator.get('url'):
        fields["抖音主页链接"] = creator['url']
    if creator.get('sec_uid'):
        fields["抖音SecUID"] = creator['sec_uid']
    
    pf = tmp / "new_creator_douyin.json"
    pf.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+record-upsert", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        
        record_id = data["data"]["record"]["record_id_list"][0] if data["data"].get("record", {}).get("record_id_list") else data["data"].get("record_id")
        return record_id
    except Exception as e:
        print(f"    写入飞书失败: {e}")
        return None
    finally:
        pf.unlink(missing_ok=True)


def main():
    config = load_config()
    
    print("连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        print("从推荐流中提取博主...")
        creators = extract_creators_from_feed(page, target_count=8)
        
        print(f"\n共找到 {len(creators)} 个博主名称")
        for i, c in enumerate(creators):
            print(f"  {i+1}. {c['name']}")
        
        # 尝试获取 sec_uid（前5个试试）
        print(f"\n尝试通过搜索获取 sec_uid（前5个）...")
        try_get_sec_uids(page, creators[:5])
        
        # 写入飞书
        print("\n写入飞书博主表...")
        added = 0
        for creator in creators:
            rec_id = add_creator_to_feishu(config, creator)
            if rec_id:
                print(f"  {creator['name']}: ✅")
                added += 1
            else:
                print(f"  {creator['name']}: ❌")
        
        print(f"\n完成! 新增 {added} 个抖音博主")
        
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
