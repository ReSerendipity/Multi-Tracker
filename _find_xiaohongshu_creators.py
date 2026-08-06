"""
通过小红书发现页找博主：提取博主名称和主页链接
"""
import json, sys, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from download_bili_following_latest import load_config, run_lark

CDP_PORT = 9334

def extract_creators_from_feed(page, target_count=8):
    """从发现流中提取博主信息"""
    creators = {}  # key: user_id
    scroll_attempts = 0
    max_attempts = 10
    
    while len(creators) < target_count and scroll_attempts < max_attempts:
        scroll_attempts += 1
        
        # 提取当前页面的博主信息
        new_creators = page.evaluate("""() => {
            const results = {};
            
            // 找所有用户主页链接
            const userLinks = document.querySelectorAll('a[href*="/user/profile/"]');
            for (const a of userLinks) {
                const href = a.href;
                const match = href.match(/\\/user\\/profile\\/([^/?#]+)/);
                if (!match) continue;
                
                const userId = match[1];
                if (userId === 'self' || userId.includes('self')) continue;
                if (results[userId]) continue;
                
                // 获取用户名
                let name = '';
                const text = a.textContent.trim();
                if (text && text.length < 30 && text.length >= 2) {
                    name = text;
                }
                
                // 尝试从父元素找用户名
                if (!name || name.length < 2) {
                    const parent = a.closest('[class*="author"], [class*="user-name"], [class*="nickname"], [class*="name"]');
                    if (parent) {
                        name = parent.textContent.trim();
                    }
                }
                
                // 过滤
                name = name.replace(/\\u00a0/g, '').trim();
                if (!name || name.length < 2 || name.length > 30) continue;
                if (name.includes('登录') || name.includes('注册') || name.includes('我的') || name.includes('更多')) continue;
                
                results[userId] = {
                    name: name,
                    user_id: userId,
                    url: 'https://www.xiaohongshu.com/user/profile/' + userId,
                };
            }
            
            return results;
        }""")
        
        for user_id, info in new_creators.items():
            if user_id not in creators:
                creators[user_id] = info
                print(f"    发现: {info['name']}")
        
        print(f"  第{scroll_attempts}次滚动，当前共 {len(creators)} 个博主")
        
        # 滚动加载更多
        if len(creators) < target_count:
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(2000)
    
    return list(creators.values())[:target_count]


def add_creator_to_feishu(config, creator):
    """添加博主到飞书表"""
    table_id = config["tables"]["creators"]["table_id"]
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    fields = {
        "博主名称": creator['name'],
        "平台": ["小红书"],
        "小红书持续跟踪": True,
    }
    
    if creator.get('url'):
        fields["小红书主页链接"] = creator['url']
    if creator.get('user_id'):
        fields["小红书用户ID"] = creator['user_id']
    
    pf = tmp / "new_creator_xhs.json"
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
    
    print("连接小红书 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开小红书发现页...")
        page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        print("从发现流中提取博主...")
        creators = extract_creators_from_feed(page, target_count=8)
        
        print(f"\n共找到 {len(creators)} 个博主")
        for i, c in enumerate(creators):
            print(f"  {i+1}. {c['name']}")
            print(f"     {c['url']}")
        
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
        
        print(f"\n完成! 新增 {added} 个小红书博主")
        
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
