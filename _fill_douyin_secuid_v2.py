"""
补全抖音博主SecUID：从精选页提取视频aweme_id，访问视频页获取作者sec_uid，更新飞书
"""
import json, sys, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from download_bili_following_latest import load_config, run_lark, list_records

CDP_PORT = 9333

def extract_video_aweme_ids(page, count=10):
    """从精选页提取视频aweme_id"""
    result = page.evaluate("""(count) => {
        const cards = document.querySelectorAll('.discover-video-card-item[data-aweme-id]');
        const results = [];
        
        for (let i = 0; i < Math.min(cards.length, count); i++) {
            const card = cards[i];
            const awemeId = card.getAttribute('data-aweme-id');
            if (awemeId) {
                results.push({
                    aweme_id: awemeId,
                    url: 'https://www.douyin.com/video/' + awemeId
                });
            }
        }
        
        return results;
    }""", count)
    
    return result


def get_author_from_video_page(page, aweme_id):
    """从视频播放页获取作者信息"""
    try:
        url = f"https://www.douyin.com/video/{aweme_id}"
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(5000)
        
        # 尝试从多个来源获取作者信息
        author_info = page.evaluate("""() => {
            // 方法1: 从用户链接中找
            const userLinks = document.querySelectorAll('a[href*="/user/"]');
            for (const a of userLinks) {
                const href = a.href;
                const match = href.match(/\\/user\\/(MS4wLjABAAA[^/?#]+|[^/?#]{20,})/);
                if (!match) continue;
                
                const secUid = match[1];
                if (secUid === 'self' || secUid.includes('self')) continue;
                
                const text = a.textContent.trim();
                if (text && text.length >= 2 && text.length <= 30) {
                    return {
                        name: text,
                        sec_uid: secUid,
                        url: href.split('?')[0]
                    };
                }
            }
            
            // 方法2: 从全局数据中找
            if (window._SSR_HYDRATED_DATA) {
                try {
                    const data = window._SSR_HYDRATED_DATA;
                    let author = null;
                    // 尝试各种路径
                    if (data.awemeDetail?.awemeInfo?.author) {
                        author = data.awemeDetail.awemeInfo.author;
                    } else if (data.videoDetail?.awemeInfo?.author) {
                        author = data.videoDetail.awemeInfo.author;
                    } else if (data.awemeDetail?.author) {
                        author = data.awemeDetail.author;
                    }
                    
                    if (author) {
                        const secUid = author.sec_uid || author.secUid;
                        if (secUid && secUid !== 'self') {
                            return {
                                name: author.nickname || author.nickName || '',
                                sec_uid: secUid,
                                url: 'https://www.douyin.com/user/' + secUid
                            };
                        }
                    }
                } catch (e) {}
            }
            
            return null;
        }""")
        
        return author_info
    except Exception as e:
        print(f"    访问视频页失败: {e}")
        return None


def add_creator_to_feishu(config, name, sec_uid, url):
    """添加博主到飞书表"""
    table_id = config["tables"]["creators"]["table_id"]
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    fields = {
        "博主名称": name,
        "平台": ["抖音"],
        "抖音主页链接": url,
        "抖音SecUID": sec_uid,
        "抖音持续跟踪": True,
    }
    
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
    
    print("检查现有抖音博主...")
    table_id = config["tables"]["creators"]["table_id"]
    rows = list_records(config, table_id, ["博主名称", "平台", "抖音SecUID", "抖音主页链接", "抖音持续跟踪"])
    
    # 统计已有sec_uid的博主
    existing_secuids = set()
    has_secuid_count = 0
    for row in rows:
        plats = row.get("平台", [])
        plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
        if "抖音" in plat_list:
            sec_uid = row.get("抖音SecUID", "") or ""
            if sec_uid and sec_uid != "self":
                existing_secuids.add(sec_uid)
                has_secuid_count += 1
    
    print(f"  已有SecUID的博主: {has_secuid_count} 个")
    
    if has_secuid_count >= 5:
        print("\n已有足够的博主，直接开始下载")
        return
    
    print("\n连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # 滚动加载更多视频
        print("滚动加载视频...")
        for i in range(3):
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(1500)
        
        # 提取视频aweme_id
        videos = extract_video_aweme_ids(page, count=15)
        print(f"找到 {len(videos)} 个视频")
        
        # 逐个访问视频页获取作者信息
        creators = {}
        for i, video in enumerate(videos):
            if len(creators) >= 5:
                break
            
            aweme_id = video['aweme_id']
            print(f"\n[{i+1}/{len(videos)}] 视频 {aweme_id}:")
            
            author = get_author_from_video_page(page, aweme_id)
            
            if author and author.get('sec_uid'):
                sec_uid = author['sec_uid']
                if sec_uid not in existing_secuids and sec_uid not in creators:
                    creators[sec_uid] = author
                    print(f"  ✅ 找到作者: {author['name']}")
                else:
                    print(f"  ⏭️  重复: {author['name']}")
            else:
                print(f"  ❌ 未找到作者信息")
        
        print(f"\n共找到 {len(creators)} 个新博主")
        for uid, info in creators.items():
            print(f"  - {info['name']}: {uid}")
        
        # 写入飞书
        print("\n写入飞书博主表...")
        added = 0
        for sec_uid, creator in creators.items():
            rec_id = add_creator_to_feishu(config, creator['name'], sec_uid, creator['url'])
            if rec_id:
                print(f"  {creator['name']}: ✅")
                added += 1
            else:
                print(f"  {creator['name']}: ❌")
        
        print(f"\n完成! 新增 {added} 个抖音博主（含完整SecUID）")
        
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
