"""清理视频表中的重复记录，只保留每条视频的一条记录"""
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


def delete_record(config, table_id, record_id):
    """删除一条记录"""
    try:
        run_lark(config, [
            "+record-delete",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--record-id", record_id,
            "--yes",
        ], timeout=30)
        return True
    except Exception as e:
        print(f"    删除失败: {e}")
        return False


def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    
    fields = ["视频标题", "平台", "平台视频ID", "BVID", "AID", "封面", "视频下载状态", "发布时间"]
    rows = list_records(config, videos_table, fields)
    
    print(f"清理前总数: {len(rows)}")
    
    # 用标题+平台作为去重键（更可靠）
    groups = defaultdict(list)
    for row in rows:
        platform = str(row.get("平台", ""))
        title = str(row.get("视频标题", "")).strip()
        key = f"{platform}|{title}"
        groups[key].append(row)
    
    # 找出重复组
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"重复组数: {len(dup_groups)}")
    
    total_deleted = 0
    total_kept = 0
    
    for key, items in dup_groups.items():
        # 排序：优先保留有封面的，其次有BVID的，再次发布时间较新的
        def sort_key(item):
            has_cover = 1 if item.get("封面") else 0
            has_bvid = 1 if item.get("BVID") else 0
            has_aid = 1 if item.get("AID") else 0
            pub_time = item.get("发布时间", "") or ""
            return (has_cover, has_bvid, has_aid, pub_time)
        
        items_sorted = sorted(items, key=sort_key, reverse=True)
        keep = items_sorted[0]
        to_delete = items_sorted[1:]
        
        title = key.split("|", 1)[1][:40]
        platform = key.split("|", 1)[0]
        print(f"\n[{platform}] {title}")
        print(f"  保留: {keep['_record_id']} (封面:{bool(keep.get('封面'))}, BVID:{bool(keep.get('BVID'))})")
        
        for item in to_delete:
            print(f"  删除: {item['_record_id']} (封面:{bool(item.get('封面'))}, BVID:{bool(item.get('BVID'))})")
            ok = delete_record(config, videos_table, item["_record_id"])
            if ok:
                total_deleted += 1
            else:
                print(f"    ⚠️  删除失败")
    
    print(f"\n=== 结果 ===")
    print(f"删除重复: {total_deleted} 条")
    print(f"保留原始: {len(rows) - total_deleted} 条")
    
    # 再次统计
    rows2 = list_records(config, videos_table, ["视频标题", "平台"])
    print(f"\n清理后总数: {len(rows2)}")
    
    groups2 = defaultdict(list)
    for row in rows2:
        key = f"{row.get('平台','')}|{str(row.get('视频标题','')).strip()}"
        groups2[key].append(row)
    
    dupes2 = {k: v for k, v in groups2.items() if len(v) > 1}
    print(f"剩余重复: {len(dupes2)} 组")


if __name__ == "__main__":
    main()
