"""确保抖音同步所需的字段都存在"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sync_douyin_to_feishu import ensure_fields, CREATOR_FIELDS, VIDEO_FIELDS
from download_bili_following_latest import load_config, field_names

def main():
    config = load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    videos_table = config["tables"]["videos"]["table_id"]
    
    print("当前博主表字段:")
    creator_fields = field_names(config, creators_table)
    for name in creator_fields:
        print(f"  - {name}")
    
    print("\n当前视频表字段:")
    video_fields = field_names(config, videos_table)
    for name in video_fields:
        print(f"  - {name}")
    
    # 扩展字段定义，添加缺失的字段
    extra_creator_fields = {
        "最近采集时间": {"type": "datetime", "name": "最近采集时间"},
    }
    
    extra_video_fields = {
        "音频文件路径": {"type": "text", "name": "音频文件路径"},
        "原始文案路径": {"type": "text", "name": "原始文案路径"},
        "清洗文案路径": {"type": "text", "name": "清洗文案路径"},
        "评论抓取状态": {"type": "text", "name": "评论抓取状态"},
        "评论文件路径": {"type": "text", "name": "评论文件路径"},
        "已抓评论数": {"type": "number", "name": "已抓评论数"},
    }
    
    # 合并字段
    all_creator_fields = {**CREATOR_FIELDS, **extra_creator_fields}
    all_video_fields = {**VIDEO_FIELDS, **extra_video_fields}
    
    # 确保字段
    print("\n确保博主表字段...")
    created = ensure_fields(config, creators_table, all_creator_fields)
    if created:
        print(f"  新增字段: {created}")
    else:
        print("  字段已齐全")
    
    print("\n确保视频表字段...")
    created = ensure_fields(config, videos_table, all_video_fields)
    if created:
        print(f"  新增字段: {created}")
    else:
        print("  字段已齐全")
    
    print("\n✅ 所有字段已确保")

if __name__ == "__main__":
    main()
