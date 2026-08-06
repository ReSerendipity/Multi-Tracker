"""给新写入的视频记录上传封面到飞书"""
import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cdp_bili_download import run_lark, load_config, VIDEOS_ROOT

config = load_config()
videos_table = config["tables"]["videos"]["table_id"]

# 刚写入的两个视频
NEW_VIDEOS = [
    ("BV1gP3y6BEhc", "12590", "recvrjWwRu5lhz"),
    ("BV1c7GA6kEqN", "946974", "recvrjWxSqZ5Wg"),
]

for bvid, mid, record_id in NEW_VIDEOS:
    video_dir = VIDEOS_ROOT / mid / bvid
    cover_files = list(video_dir.glob("*.cover.jpg")) + list(video_dir.glob("*cover*.png"))
    if not cover_files:
        print(f"{bvid}: 未找到封面文件")
        continue
    
    cover_path = cover_files[0]
    print(f"上传 {bvid} 封面: {cover_path.name}")
    
    try:
        data = run_lark(config, [
            "+record-upload-attachment",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", videos_table,
            "--record-id", record_id,
            "--field-id", "封面",
            "--file", str(cover_path.relative_to(ROOT)),
        ], timeout=60)
        print(f"  ✅ 上传成功")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

print("\n完成!")
