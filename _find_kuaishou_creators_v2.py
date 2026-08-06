"""
优化快手博主发现：点击视频从播放页提取博主信息
"""
import json, sys, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from download_bili_following_latest import load_config, run_lark

CDP_PORT = 9335

def extract_creator_from_video_page(page):
    """从视频播放页提取博主信息"""
    result = page.evaluate("""() => {
        // 找个人主页链接
        const profileLinks = document.querySelectorAll('a[href*="/profile/"]');
        for (const a of profileLinks) {
            const href = a.href;
            const match = href.match(/\\/profile\\/([^/?#]+)/);
            if (!match) continue;
            
            const userId = match[1];
            if (userId === 'self' || userId.includes('self')) continue;
            
            // 获取用户名
            let name = '';
            const text = a.textContent.trim();
            if (text.startsWith('@')) {
                name = text.slice(1).trim();
            } else if (text && text.length < 30 && text.length >= 2) {
                name = text;
            }
            
            // 从附近元素找用户名
            if (!name || name.length < 2) {
                const parent = a.closest('[class*="author"], [class*="user-info"], [class*="profile"]');
                if (parent) {
                    const nameEl = parent.querySelector('[class*="name"], [class*="nickname"]');
                    if (nameEl) {
                        name = nameEl.textContent.trim();
                    }
                }
            }
            
            name = name.replace(/\\u00a0/g, '').trim();
            if (name && name.length >= 2 && name.length <= 30) {
                return {
                    name: name,
                    user_id: userId,
                    url: 'https://www.kuaishou.com/profile/' + userId,
                };
            }
        }
        
        return null;
    }""")
    
    return result


def extract_creators_from_feed(page, target_count=8):
    """从推荐流中提取博主信息（点击视频获取）"""
    creators = {}  # key: user_id
    video_index = 0
    max_videos = 20
    
    # 先找所有视频卡片
    video_count = page.evaluate("""() => {
        const videos = document.querySelectorAll('[class*="video-card"], [class*="feed-item"], video');
        return videos.length;
    }""")
    
    print(f"  找到 {video_count} 个视频元素")
    
    while len(creators) < target_count and video_index < max_videos:
        video_index += 1
        
        try:
            # 点击第 N 个视频
            result = page.evaluate("""(index) => {
                const videos = document.querySelectorAll('[class*="video-card"], [class*="feed-item"], video');
                if (index >= videos.length) return { clicked: false, reason: 'no more videos' };
                
                const video = videos[index];
                // 滚动到视图
                video.scrollIntoView({ behavior: 'smooth', block: 'center' });
                
                // 尝试点击
                setTimeout(() => video.click(), 500);
                
                return { clicked: true };
            }""", video_index - 1)
            
            if not result.get('clicked'):
                print(f"  视频 #{video_index}: 无法点击")
                continue
            
            page.wait_for_timeout(3000)
            
            # 提取博主信息
            creator = extract_creator_from_video_page(page)
            
            if creator and creator['user_id'] not in creators:
                creators[creator['user_id']] = creator
                print(f"    发现: {creator['name']}")
            else:
                print(f"  视频 #{video_index}: 未找到新博主")
            
            # 返回首页
            if 'profile' in page.url or 'video' in page.url or 'short-video' in page.url:
                page.go_back(wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"  视频 #{video_index}: 出错 - {e}")
            # 确保返回首页
            if 'kuaishou.com' in page.url and 'www.kuaishou.com' not in page.url.split('/')[-1]:
                try:
                    page.go_back(wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                except:
                    pass
    
    return list(creators.values())[:target_count]


def add_creator_to_feishu(config, creator):
    """添加博主到飞书表"""
    table_id = config["tables"]["creators"]["table_id"]
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    fields = {
        "博主名称": creator['name'],
        "平台": ["快手"],
        "快手持续跟踪": True,
    }
    
    if creator.get('url'):
        fields["快手主页链接"] = creator['url']
    if creator.get('user_id'):
        fields["快手用户ID"] = creator['user_id']
    
    pf = tmp / "new_creator_ks.json"
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
    
    print("连接快手 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开快手首页...")
        page.goto("https://www.kuaishou.com", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        print("从视频播放页提取博主...")
        creators = extract_creators_from_feed(page, target_count=5)
        
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
        
        print(f"\n完成! 新增 {added} 个快手博主")
        
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
