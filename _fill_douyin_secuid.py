"""
补全抖音博主的SecUID：从视频播放页获取作者sec_uid并更新飞书
"""
import json, sys, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from download_bili_following_latest import load_config, run_lark, list_records

CDP_PORT = 9333

def get_douyin_creators_without_secuid(config):
    """获取没有SecUID的抖音博主"""
    table_id = config["tables"]["creators"]["table_id"]
    rows = list_records(config, table_id, ["博主名称", "平台", "抖音SecUID", "抖音主页链接", "抖音持续跟踪"])
    
    result = []
    for row in rows:
        plats = row.get("平台", [])
        plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
        if "抖音" in plat_list:
            sec_uid = row.get("抖音SecUID", "") or ""
            if not sec_uid or sec_uid == "self":
                continue  # 跳过没有sec_uid的和自己
            result.append(row)
    
    # 再找没有sec_uid的
    no_secuid = []
    for row in rows:
        plats = row.get("平台", [])
        plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
        if "抖音" in plat_list:
            sec_uid = row.get("抖音SecUID", "") or ""
            if not sec_uid or sec_uid == "self":
                name = row.get("博主名称", "")
                if name and name != "我的":  # 跳过"我的"
                    no_secuid.append({
                        "record_id": row["record_id"],
                        "name": name,
                    })
    
    return no_secuid


def close_login_popup(page):
    """尝试关闭登录弹窗"""
    try:
        # 按ESC
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        
        # 找关闭按钮
        close_selectors = [
            '.login-close',
            '[class*="login"] [class*="close"]',
            '.dy-modal .dy-icon-close',
            '[data-e2e="login-close"]',
        ]
        for sel in close_selectors:
            btns = page.query_selector_all(sel)
            for btn in btns:
                try:
                    if btn.is_visible():
                        btn.click(force=True)
                        page.wait_for_timeout(500)
                        return True
                except:
                    continue
        return False
    except:
        return False


def get_sec_uid_from_first_video(page):
    """从精选页点击第一个视频，从播放页获取作者sec_uid"""
    try:
        # 点击第一个视频卡片
        first_card = page.query_selector('.discover-video-card-item')
        if not first_card:
            return None, None, None
        
        first_card.click()
        page.wait_for_timeout(5000)
        
        # 检查URL
        url = page.url
        print(f"    视频页URL: {url}")
        
        # 从页面中找作者信息
        author_info = page.evaluate("""() => {
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
                    return {
                        name: text,
                        sec_uid: secUid,
                        url: href
                    };
                }
            }
            
            // 尝试从 window 全局对象找
            if (window._SSR_HYDRATED_DATA) {
                try {
                    const data = window._SSR_HYDRATED_DATA;
                    // 尝试找作者信息
                    const author = data?.awemeDetail?.awemeInfo?.author;
                    if (author) {
                        return {
                            name: author.nickname || author.unique_id,
                            sec_uid: author.sec_uid,
                            url: author.sec_uid ? 'https://www.douyin.com/user/' + author.sec_uid : ''
                        };
                    }
                } catch (e) {}
            }
            
            return null;
        }""")
        
        if author_info:
            return author_info.get("name"), author_info.get("sec_uid"), author_info.get("url")
        
        return None, None, None
    except Exception as e:
        print(f"    获取作者信息失败: {e}")
        return None, None, None


def update_creator_secuid(config, record_id, name, sec_uid, url):
    """更新飞书博主的SecUID"""
    table_id = config["tables"]["creators"]["table_id"]
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    fields = {
        "抖音SecUID": sec_uid,
        "抖音主页链接": url,
    }
    
    pf = tmp / "update_douyin_secuid.json"
    pf.write_text(json.dumps({"fields": fields, "record_id": record_id}), ensure_ascii=False)
    
    try:
        data = run_lark(config, [
            "+record-update", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--record-id", record_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        return True
    except Exception as e:
        print(f"    更新飞书失败: {e}")
        return False
    finally:
        pf.unlink(missing_ok=True)


def main():
    config = load_config()
    
    # 获取有完整sec_uid的博主（已有的）和没有的
    # 先看看有多少有sec_uid的
    print("检查抖音博主SecUID情况...")
    table_id = config["tables"]["creators"]["table_id"]
    rows = list_records(config, table_id, ["博主名称", "平台", "抖音SecUID", "抖音主页链接", "抖音持续跟踪"])
    
    has_secuid = []
    no_secuid = []
    for row in rows:
        plats = row.get("平台", [])
        plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
        if "抖音" in plat_list:
            name = row.get("博主名称", "")
            sec_uid = row.get("抖音SecUID", "") or ""
            if sec_uid and sec_uid != "self" and name != "我的":
                has_secuid.append(row)
            elif name and name != "我的":
                no_secuid.append(row)
    
    print(f"  已有SecUID: {len(has_secuid)} 个")
    print(f"  缺少SecUID: {len(no_secuid)} 个")
    
    if has_secuid:
        print("\n已有SecUID的博主:")
        for row in has_secuid:
            print(f"  - {row['博主名称']}: {row['抖音SecUID']}")
    
    # 如果有sec_uid的博主，直接开始下载
    if len(has_secuid) >= 3:
        print(f"\n已有 {len(has_secuid)} 个博主有SecUID，可以直接开始下载")
        return
    
    # 否则尝试补全
    print("\n尝试补全抖音博主SecUID...")
    print("连接抖音 CDP 浏览器...")
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        print("打开抖音精选...")
        page.goto("https://www.douyin.com/jingxuan", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # 关闭登录弹窗
        close_login_popup(page)
        
        # 从视频播放页获取作者信息（获取5个）
        creators_found = []
        video_count = 0
        max_videos = 15
        
        while len(creators_found) < 5 and video_count < max_videos:
            video_count += 1
            print(f"\n  视频 #{video_count}:")
            
            name, sec_uid, url = get_sec_uid_from_first_video(page)
            
            if name and sec_uid:
                # 检查是否重复
                if not any(c['sec_uid'] == sec_uid for c in creators_found):
                    creators_found.append({
                        'name': name,
                        'sec_uid': sec_uid,
                        'url': url
                    })
                    print(f"    ✅ 找到: {name}")
                else:
                    print(f"    重复: {name}")
            else:
                print(f"    未找到作者信息")
            
            # 返回精选页并下划一个视频
            if 'jingxuan' not in page.url:
                page.go_back(wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                close_login_popup(page)
            
            # 滚动到下一个视频
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(2000)
        
        print(f"\n共找到 {len(creators_found)} 个博主的完整信息")
        for c in creators_found:
            print(f"  - {c['name']}: {c['sec_uid']}")
        
        # 写入飞书（新增博主）
        print("\n写入飞书博主表...")
        added = 0
        for creator in creators_found:
            # 检查是否已存在
            exists = False
            for row in rows:
                if row.get("抖音SecUID") == creator['sec_uid']:
                    exists = True
                    break
            
            if exists:
                print(f"  {creator['name']}: 已存在，跳过")
                continue
            
            # 新增
            fields = {
                "博主名称": creator['name'],
                "平台": ["抖音"],
                "抖音主页链接": creator['url'],
                "抖音SecUID": creator['sec_uid'],
                "抖音持续跟踪": True,
            }
            
            tmp = ROOT / ".tmp-lark"
            tmp.mkdir(exist_ok=True)
            pf = tmp / "new_creator_douyin.json"
            pf.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
            
            try:
                data = run_lark(config, [
                    "+record-upsert", "--as", "user",
                    "--base-token", config["base_token"],
                    "--table-id", table_id,
                    "--json", f"@{pf.relative_to(ROOT)}",
                ], timeout=30)
                
                rec_id = data["data"]["record"]["record_id_list"][0] if data["data"].get("record", {}).get("record_id_list") else data["data"].get("record_id")
                if rec_id:
                    print(f"  {creator['name']}: ✅ 新增")
                    added += 1
            except Exception as e:
                print(f"  {creator['name']}: ❌ {e}")
            finally:
                pf.unlink(missing_ok=True)
        
        print(f"\n完成! 新增 {added} 个抖音博主（含完整SecUID）")
        
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
