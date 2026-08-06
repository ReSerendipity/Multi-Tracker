"""
确保飞书博主表和视频表包含所有平台所需字段
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sync_douyin_to_feishu import ensure_fields as ensure_douyin_fields, CREATOR_FIELDS as DOUYIN_CREATOR_FIELDS, VIDEO_FIELDS as DOUYIN_VIDEO_FIELDS
from sync_kuaishou_to_feishu import ensure_fields as ensure_kuaishou_fields, CREATOR_FIELDS as KUAISHOU_CREATOR_FIELDS, VIDEO_FIELDS as KUAISHOU_VIDEO_FIELDS
from sync_xiaohongshu_to_feishu import ensure_fields as ensure_xiaohongshu_fields, CREATOR_FIELDS as XHS_CREATOR_FIELDS, VIDEO_FIELDS as XHS_VIDEO_FIELDS
from download_bili_following_latest import load_config

def main():
    config = load_config()
    creators_table_id = config["tables"]["creators"]["table_id"]
    videos_table_id = config["tables"]["videos"]["table_id"]
    
    print("确保博主表字段...")
    
    # 合并所有平台的博主字段
    all_creator_fields = {}
    
    # 抖音字段
    for name, spec in DOUYIN_CREATOR_FIELDS.items():
        all_creator_fields[name] = spec
    
    # 快手字段（合并平台选项）
    for name, spec in KUAISHOU_CREATOR_FIELDS.items():
        if name == "平台":
            # 合并选项
            existing = all_creator_fields.get("平台", {"type": "select", "name": "平台", "multiple": True, "options": []})
            existing_options = {o["name"] for o in existing.get("options", [])}
            for opt in spec.get("options", []):
                if opt["name"] not in existing_options:
                    existing["options"].append(opt)
            all_creator_fields["平台"] = existing
        else:
            all_creator_fields[name] = spec
    
    # 小红书字段（合并平台选项）
    for name, spec in XHS_CREATOR_FIELDS.items():
        if name == "平台":
            existing = all_creator_fields.get("平台", {"type": "select", "name": "平台", "multiple": True, "options": []})
            existing_options = {o["name"] for o in existing.get("options", [])}
            for opt in spec.get("options", []):
                if opt["name"] not in existing_options:
                    existing["options"].append(opt)
            all_creator_fields["平台"] = existing
        else:
            all_creator_fields[name] = spec
    
    created = ensure_douyin_fields(config, creators_table_id, all_creator_fields)
    if created:
        print(f"  博主表新增字段: {created}")
    else:
        print("  博主表字段已齐全")
    
    print("\n确保视频表字段...")
    
    # 合并所有平台的视频字段
    all_video_fields = {}
    
    for name, spec in DOUYIN_VIDEO_FIELDS.items():
        all_video_fields[name] = spec
    
    for name, spec in KUAISHOU_VIDEO_FIELDS.items():
        if name == "平台":
            existing = all_video_fields.get("平台", {"type": "select", "name": "平台", "multiple": False, "options": []})
            existing_options = {o["name"] for o in existing.get("options", [])}
            for opt in spec.get("options", []):
                if opt["name"] not in existing_options:
                    existing["options"].append(opt)
            all_video_fields["平台"] = existing
        elif name not in all_video_fields:
            all_video_fields[name] = spec
    
    for name, spec in XHS_VIDEO_FIELDS.items():
        if name == "平台":
            existing = all_video_fields.get("平台", {"type": "select", "name": "平台", "multiple": False, "options": []})
            existing_options = {o["name"] for o in existing.get("options", [])}
            for opt in spec.get("options", []):
                if opt["name"] not in existing_options:
                    existing["options"].append(opt)
            all_video_fields["平台"] = existing
        elif name not in all_video_fields:
            all_video_fields[name] = spec
    
    created = ensure_douyin_fields(config, videos_table_id, all_video_fields)
    if created:
        print(f"  视频表新增字段: {created}")
    else:
        print("  视频表字段已齐全")
    
    print("\n✅ 所有平台字段已确保")

if __name__ == "__main__":
    main()
