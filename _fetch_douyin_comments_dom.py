"""
直接用Playwright从抖音视频页抓取评论（DOM方式）
"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark, list_records

CDP_PORT = 9333

def fetch_comments_dom(page, aweme_id, max_comments=50):
    """从视频播放页DOM中抓取评论"""
    url = f"https://www.douyin.com/video/{aweme_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    time.sleep(5)
    
    comments = []
    
    # 先检查是否有评论区
    has_comments = page.evaluate("""() => {
        const commentElements = document.querySelectorAll('[class*="comment"], [class*="Comment"]');
        return commentElements.length > 0;
    }""")
    
    if not has_comments:
        print(f"    未找到评论区元素")
        return []
    
    # 滚动加载更多评论
    last_count = 0
    scroll_attempts = 0
    max_attempts = 10
    
    while len(comments) < max_comments and scroll_attempts < max_attempts:
        scroll_attempts += 1
        
        # 提取当前可见评论
        new_comments = page.evaluate("""() => {
            const results = [];
            
            // 找评论项
            const commentItems = document.querySelectorAll('[class*="comment-item"], [class*="CommentItem"], [class*="comment-main"]');
            
            for (const item of commentItems) {
                try {
                    // 提取用户名
                    let userName = '';
                    const nameEl = item.querySelector('[class*="user-name"], [class*="nickname"], [class*="name"], [class*="UserName"]');
                    if (nameEl) userName = nameEl.textContent.trim();
                    
                    // 提取评论内容
                    let content = '';
                    const contentEl = item.querySelector('[class*="comment-content"], [class*="content"], [class*="CommentContent"], [class*="text"]');
                    if (contentEl) content = contentEl.textContent.trim();
                    
                    // 提取点赞数
                    let likeCount = 0;
                    const likeEl = item.querySelector('[class*="like"], [class*="digg"], [class*="praise"]');
                    if (likeEl) {
                        const likeText = likeEl.textContent.trim();
                        const numMatch = likeText.match(/(\\d+)/);
                        if (numMatch) likeCount = parseInt(numMatch[1]);
                    }
                    
                    if (userName && content && content.length > 0) {
                        results.push({
                            user_name: userName,
                            text: content,
                            like_count: likeCount,
                        });
                    }
                } catch (e) {}
            }
            
            return results;
        }""")
        
        for c in new_comments:
            # 去重（基于用户名+内容前50字）
            key = c['user_name'] + '|' + c['text'][:50]
            if not any(x['user_name'] + '|' + x['text'][:50] == key for x in comments):
                comments.append(c)
        
        print(f"    第{scroll_attempts}次滚动，当前 {len(comments)} 条评论")
        
        if len(comments) == last_count:
            # 没有新评论，可能已经到底了
            break
        last_count = len(comments)
        
        # 滚动评论区
        page.evaluate("""() => {
            // 找评论容器并滚动
            const containers = document.querySelectorAll('[class*="comment-list"], [class*="CommentList"], [class*="comments"]');
            if (containers.length > 0) {
                containers[0].scrollTop = containers[0].scrollHeight;
            } else {
                window.scrollBy(0, 500);
            }
        }""")
        time.sleep(1500)
    
    return comments[:max_comments]


def save_comments(comments, out_dir, aweme_id):
    """保存评论到文件"""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # JSONL格式
    jsonl_path = out_dir / "comments.jsonl"
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for c in comments:
            f.write(json.dumps({
                "user_name": c["user_name"],
                "text": c["text"],
                "like_count": c["like_count"],
                "aweme_id": aweme_id,
            }, ensure_ascii=False) + '\n')
    
    # JSON格式（带元数据）
    json_path = out_dir / "comments.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "aweme_id": aweme_id,
            "total": len(comments),
            "comments": comments,
        }, f, ensure_ascii=False, indent=2)
    
    return jsonl_path


def update_video_comments(config, record_id, comments_path, comment_count):
    """更新飞书视频的评论信息"""
    table_id = config["tables"]["videos"]["table_id"]
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    fields = {
        "评论抓取状态": "已抓取" if comment_count > 0 else "未抓取",
        "评论文件路径": str(comments_path) if comments_path else "",
        "已抓评论数": int(comment_count),
    }
    
    pf = tmp / "update_comments.json"
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
    
    print("从飞书获取抖音视频列表...")
    table_id = config["tables"]["videos"]["table_id"]
    fields = ["平台", "平台视频ID", "视频标题", "评论抓取状态", "评论文件路径", "已抓评论数"]
    rows = list_records(config, table_id, fields)
    
    douyin_videos = []
    for row in rows:
        platform = row.get("平台", "")
        if str(platform) == "抖音":
            douyin_videos.append(row)
    
    print(f"找到 {len(douyin_videos)} 个抖音视频")
    
    # 只处理还没抓取评论的
    to_fetch = []
    for v in douyin_videos:
        status = v.get("评论抓取状态", "") or ""
        if status != "已抓取":
            to_fetch.append(v)
    
    print(f"需要抓取评论的: {len(to_fetch)} 个")
    
    if not to_fetch:
        print("所有视频都已抓取评论，无需处理")
        return
    
    print("\n连接抖音 CDP 浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        success_count = 0
        for i, video in enumerate(to_fetch):
            aweme_id = video.get("平台视频ID", "")
            title = video.get("视频标题", "")[:30]
            record_id = video.get("record_id", "")
            
            print(f"\n[{i+1}/{len(to_fetch)}] {aweme_id}: {title}")
            
            if not aweme_id:
                print("  ⚠️  缺少视频ID，跳过")
                continue
            
            # 输出目录
            out_dir = ROOT / "downloads" / "douyin-comments" / aweme_id
            
            # 抓取评论
            comments = fetch_comments_dom(page, aweme_id, max_comments=50)
            comment_count = len(comments)
            
            if comment_count > 0:
                print(f"  ✅ 抓取到 {comment_count} 条评论")
                
                # 保存
                comments_path = save_comments(comments, out_dir, aweme_id)
                
                # 更新飞书
                if record_id:
                    ok = update_video_comments(config, record_id, comments_path, comment_count)
                    if ok:
                        success_count += 1
                        print(f"  ✅ 飞书已更新")
                    else:
                        print(f"  ❌ 飞书更新失败")
            else:
                print(f"  ⚠️  未抓取到评论")
        
        print(f"\n完成! 成功抓取并更新 {success_count}/{len(to_fetch)} 个视频的评论")
        
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
