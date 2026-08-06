"""在飞书表中创建抖音字段"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sync_douyin_to_feishu import ensure_fields, CREATOR_FIELDS, VIDEO_FIELDS
from download_bili_following_latest import load_config

config = load_config()

print("创建博主表字段...")
creator_fields = ensure_fields(config, config["tables"]["creators"]["table_id"], CREATOR_FIELDS, dry_run=False)
print(f"  新建: {len(creator_fields)} 个字段")
for f in creator_fields:
    print(f"    - {f}")

print("\n创建视频表字段...")
video_fields = ensure_fields(config, config["tables"]["videos"]["table_id"], VIDEO_FIELDS, dry_run=False)
print(f"  新建: {len(video_fields)} 个字段")
for f in video_fields:
    print(f"    - {f}")

print("\n完成!")
