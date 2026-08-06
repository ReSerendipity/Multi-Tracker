"""
批量抓取抖音视频评论，并更新飞书
"""
import json, sys, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark, list_records

CDP_PORT = 9333
COMMENT_SCRIPT = ROOT / ".agents" / "skills" / "douyin-comments" / "scripts" / "fetch_douyin_comments.py"

def get_douyin_videos_from_feishu(config):
    """从飞书获取抖音视频列表"""
    table_id = config["tables"]["videos"]["table_id"]
    fields = ["平台", "平台视频ID", "视频链接", "视频标题", "评论抓取状态", "评论文件路径", "已抓评论数"]
    rows = list_records(config, table_id, fields)
    
    douyin_videos = []
    for row in rows:
        platform = row.get("平台", "")
        if str(platform) == "抖音":
            douyin_videos.append(row)
    
    return douyin_videos


def fetch_comments(aweme_id, out_dir, max_comments=50):
    """抓取单个视频的评论"""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    env = os.environ.copy()
    env["CDP_WS_URL"] = f"ws://127.0.0.1:{CDP_PORT}/devtools/browser/18543009-3930-4502-a097-84d6e40ad5f4"
    
    cmd = [
        sys.executable,
        str(COMMENT_SCRIPT),
        "--aweme-id", aweme_id,
        "--out-dir", str(out_dir),
        "--max-comments", str(max_comments),
        "--max-pages", "3",
        "--cdp-port", str(CDP_PORT),
        "--no-replies",
    ]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode != 0:
            print(f"    评论抓取失败: {result.stderr[:200]}")
            return None, 0
        
        # 读取评论数
        comments_path = out_dir / "comments.jsonl"
        if comments_path.exists():
            count = sum(1 for _ in open(comments_path, 'r', encoding='utf-8'))
            return comments_path, count
        
        # 也可能是 comments-all.jsonl
        comments_all_path = out_dir / "comments-all.jsonl"
        if comments_all_path.exists():
            count = sum(1 for _ in open(comments_all_path, 'r', encoding='utf-8'))
            return comments_all_path, count
        
        return None, 0
        
    except subprocess.TimeoutExpired:
        print(f"    评论抓取超时")
        return None, 0
    except Exception as e:
        print(f"    评论抓取出错: {e}")
        return None, 0


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
    videos = get_douyin_videos_from_feishu(config)
    
    print(f"找到 {len(videos)} 个抖音视频")
    
    # 只处理还没抓取评论的
    to_fetch = []
    for v in videos:
        status = v.get("评论抓取状态", "") or ""
        if status != "已抓取":
            to_fetch.append(v)
    
    print(f"需要抓取评论的: {len(to_fetch)} 个")
    
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
        comments_path, comment_count = fetch_comments(aweme_id, out_dir, max_comments=50)
        
        if comments_path and comment_count > 0:
            print(f"  ✅ 抓取到 {comment_count} 条评论")
            
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


if __name__ == "__main__":
    main()
