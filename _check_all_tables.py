"""全面检查各表现状"""
import sys, json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, field_names, list_records

def main():
    config = load_config()
    
    # 1. 博主表
    print("=" * 60)
    print("【博主表】")
    print("=" * 60)
    creators_table = config["tables"]["creators"]["table_id"]
    c_fields = field_names(config, creators_table)
    print(f"字段数: {len(c_fields)}")
    for name, info in c_fields.items():
        print(f"  {name}: {info['type']}")
    
    creator_rows = list_records(config, creators_table, list(c_fields.keys()))
    print(f"\n总博主数: {len(creator_rows)}")
    
    # 统计各平台博主数量
    bili_count = sum(1 for r in creator_rows if r.get("B站MID"))
    dy_count = sum(1 for r in creator_rows if r.get("抖音SecUID"))
    xhs_count = sum(1 for r in creator_rows if r.get("小红书用户ID"))
    ks_count = sum(1 for r in creator_rows if r.get("快手用户ID"))
    print(f"  B站博主: {bili_count}")
    print(f"  抖音博主: {dy_count}")
    print(f"  小红书博主: {xhs_count}")
    print(f"  快手博主: {ks_count}")
    
    # 看看B站博主有没有其他平台的冗余字段
    bili_creators = [r for r in creator_rows if r.get("B站MID")]
    print(f"\n前3个B站博主字段填充情况:")
    for r in bili_creators[:3]:
        print(f"  {r.get('博主名称', '')}")
        for fname in ["B站MID", "抖音SecUID", "小红书用户ID", "快手用户ID", "抖音主页链接", "小红书主页链接", "快手主页链接", "主页链接"]:
            val = r.get(fname, "")
            if val:
                print(f"    {fname}: {str(val)[:50]}")
    
    # 2. 视频快照表
    print("\n" + "=" * 60)
    print("【视频快照表】")
    print("=" * 60)
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    try:
        s_fields = field_names(config, snapshot_table)
        print(f"字段数: {len(s_fields)}")
        for name, info in s_fields.items():
            print(f"  {name}: {info['type']}")
        
        snapshot_rows = list_records(config, snapshot_table, list(s_fields.keys()))
        print(f"\n总快照数: {len(snapshot_rows)}")
        
        # 检查重复
        snap_groups = defaultdict(list)
        for r in snapshot_rows:
            vid = str(r.get("关联视频", "") or r.get("视频BVID", "") or r.get("平台视频ID", ""))
            time = str(r.get("快照时间", "") or r.get("采集时间", ""))
            key = f"{vid}|{time}"
            snap_groups[key].append(r["_record_id"])
        
        dupes = {k: v for k, v in snap_groups.items() if len(v) > 1}
        print(f"重复快照组: {len(dupes)}")
    except Exception as e:
        print(f"  读取失败: {e}")
    
    # 3. 评论表
    print("\n" + "=" * 60)
    print("【评论表】")
    print("=" * 60)
    comments_table = config["tables"]["video_comments"]["table_id"]
    try:
        cm_fields = field_names(config, comments_table)
        print(f"字段数: {len(cm_fields)}")
        for name, info in cm_fields.items():
            print(f"  {name}: {info['type']}")
        
        comment_rows = list_records(config, comments_table, list(cm_fields.keys()))
        print(f"\n总评论数: {len(comment_rows)}")
    except Exception as e:
        print(f"  读取失败: {e}")


if __name__ == "__main__":
    main()
