"""补写之前下载失败的视频记录到飞书"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cdp_bili_download import (
    run_lark, load_config, create_video_record, create_metric_snapshot,
    load_creators, VIDEOS_ROOT
)

# 之前失败的视频
FAILED = [
    ("epcdiy", "12590", "BV1gP3y6BEhc"),
    ("影视飓风", "946974", "BV1c7GA6kEqN"),
]

config = load_config()
creators = load_creators(config)

for name, mid, bvid in FAILED:
    creator = next((c for c in creators if c["mid"] == mid), None)
    if not creator:
        print(f"{name}: 博主不存在，跳过")
        continue
    
    video_dir = VIDEOS_ROOT / mid / bvid
    if not video_dir.exists():
        print(f"{bvid}: 目录不存在 {video_dir}")
        continue
    
    # 查找文件
    media_files = list(video_dir.glob("*.mp4"))
    info_files = list(video_dir.glob("*.info.json"))
    desc_files = list(video_dir.glob("*.description"))
    cover_files = list(video_dir.glob("*cover*")) + list(video_dir.glob("*.jpg")) + list(video_dir.glob("*.png"))
    cover_files = [f for f in cover_files if not f.name.startswith(".")]
    comment_files = list(video_dir.glob("*comment*")) + list(video_dir.glob("comments*"))
    
    media_path = media_files[0] if media_files else None
    info_path = info_files[0] if info_files else None
    desc_path = desc_files[0] if desc_files else None
    cover_path = cover_files[0] if cover_files else None
    
    # 统计评论数
    comment_count = 0
    comments_path = None
    for cf in video_dir.glob("*comment*.jsonl"):
        comments_path = cf
        with open(cf, "r", encoding="utf-8") as f:
            comment_count = sum(1 for _ in f)
        break
    
    # 读取视频信息，转换为脚本需要的格式
    video_info = None
    if info_path and info_path.exists():
        with open(info_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # yt-dlp info.json 格式转换为脚本需要的格式
        video_info = {
            "bvid": raw.get("id", raw.get("display_id", bvid)),
            "aid": raw.get("id", ""),
            "title": raw.get("title", ""),
            "duration": raw.get("duration", 0),
            "pubdate": raw.get("timestamp", 0),
            "description": raw.get("description", ""),
            "stat": {
                "view": raw.get("view_count", 0),
                "like": raw.get("like_count", 0),
                "coin": raw.get("like_count", 0),  # yt-dlp info 里没有 coin，用 like 近似
                "favorite": raw.get("comment_count", 0),  # 同上
                "share": 0,
                "reply": raw.get("comment_count", 0),
                "danmaku": 0,
            }
        }
    
    if not video_info:
        print(f"{bvid}: 缺少 info.json，跳过")
        continue
    
    # 读取统计数据
    stat = video_info.get("stat", {})
    
    print(f"处理 {name} - {bvid}")
    print(f"  视频: {media_path.name if media_path else 'N/A'}")
    print(f"  封面: {cover_path.name if cover_path else 'N/A'}")
    print(f"  评论: {comment_count} 条")
    
    try:
        record_id = create_video_record(
            config, creator, video_info,
            media_path, info_path, desc_path, cover_path,
            comments_path if comment_count > 0 else None, comment_count
        )
        print(f"  视频记录ID: {record_id}")
        
        snapshot_id = create_metric_snapshot(config, record_id, stat, bvid)
        print(f"  快照记录ID: {snapshot_id}")
        print(f"  ✅ 成功")
    except Exception as e:
        print(f"  ❌ 失败: {e}")
    print()
