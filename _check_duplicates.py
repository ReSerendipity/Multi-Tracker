"""检查视频表中的重复数据"""
import sys, json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records

def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    
    fields = ["视频标题", "平台", "平台视频ID", "BVID", "视频链接"]
    rows = list_records(config, videos_table, fields)
    
    print(f"总视频数: {len(rows)}")
    
    # 按平台+平台视频ID 检查重复
    id_map = defaultdict(list)
    title_map = defaultdict(list)
    
    for row in rows:
        platform = str(row.get("平台", ""))
        vid = str(row.get("平台视频ID", ""))
        bvid = str(row.get("BVID", ""))
        title = str(row.get("视频标题", ""))
        rid = row.get("_record_id", "")
        
        key = f"{platform}|{vid or bvid}"
        id_map[key].append({"title": title, "record_id": rid})
        
        title_key = f"{platform}|{title}"
        title_map[title_key].append({"vid": vid, "record_id": rid})
    
    # ID重复的
    id_dupes = {k: v for k, v in id_map.items() if len(v) > 1}
    print(f"\n按平台+视频ID 重复的: {len(id_dupes)} 组")
    for key, items in id_dupes.items():
        print(f"  {key}: {len(items)} 条")
        for item in items:
            print(f"    - {item['record_id']} | {item['title'][:30]}")
    
    # 标题重复的
    title_dupes = {k: v for k, v in title_map.items() if len(v) > 1}
    print(f"\n按平台+标题 重复的: {len(title_dupes)} 组")
    for key, items in list(title_dupes.items())[:10]:
        print(f"  {key[:50]}: {len(items)} 条")
        for item in items:
            print(f"    - {item['record_id']} | {item['vid']}")
    
    if len(title_dupes) > 10:
        print(f"  ... 还有 {len(title_dupes)-10} 组")


if __name__ == "__main__":
    main()
