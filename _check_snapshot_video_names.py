"""
检查快照表前几条数据，看看为什么没有视频名称
以及视频表的主字段是什么
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, field_names, list_records


def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    
    # 看看视频表字段列表，第一个字段就是主字段
    v_fields = field_names(config, videos_table)
    print("视频表字段（第一个是主字段）:")
    for i, (name, info) in enumerate(v_fields.items()):
        marker = " ← 主字段" if i == 0 else ""
        print(f"  {i+1}. {name}: {info['type']}{marker}")
    
    # 看看快照表前5条
    print("\n快照表前5条:")
    s_fields = ["关联视频", "快照时间", "播放量", "备注"]
    rows = list_records(config, snapshot_table, s_fields)
    # 按时间倒序
    rows.sort(key=lambda r: r.get("快照时间", ""), reverse=True)
    
    for i, row in enumerate(rows[:5]):
        link = row.get("关联视频")
        vid_info = ""
        if link and isinstance(link, list) and len(link) > 0:
            item = link[0]
            if isinstance(item, dict):
                vid_info = f"record_id={item.get('record_id', '')}, text={str(item.get('text', ''))[:30]}"
            else:
                vid_info = str(item)[:50]
        print(f"  {i+1}. {row.get('快照时间', '')} | 关联视频: {vid_info or '空'} | {row.get('备注', '')}")


if __name__ == "__main__":
    main()
