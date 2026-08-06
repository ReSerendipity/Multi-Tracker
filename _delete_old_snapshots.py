"""删除旧的快照（71条规整的那些），只保留新生成的89条"""
import sys, json, time
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


def delete_batch(config, table_id, record_ids):
    """批量删除记录（用JSON方式）"""
    if not record_ids:
        return 0
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"del_snap.json"
    pf.write_text(json.dumps({"record_id_list": record_ids}), encoding="utf-8")
    
    try:
        run_lark(config, [
            "+record-delete",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{pf.relative_to(ROOT)}",
            "--yes",
        ], timeout=30)
        pf.unlink(missing_ok=True)
        return len(record_ids)
    except Exception as e:
        print(f"  删除失败: {e}")
        pf.unlink(missing_ok=True)
        return 0


def main():
    config = load_config()
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    
    # 获取所有快照
    s_fields = ["备注", "快照时间"]
    all_snaps = list_records(config, snapshot_table, s_fields)
    print(f"总快照数: {len(all_snaps)}")
    
    # 旧的快照备注格式: "14天前快照", "7天前快照", "最新快照"
    # 新的快照备注格式: "最新快照", "X天前数据"
    # 区分方式：旧的都带"快照"后缀且天数是规整的(0,7,14)
    old_ids = []
    new_ids = []
    
    for s in all_snaps:
        remark = str(s.get("备注", ""))
        # 旧的: "14天前快照", "7天前快照", "最新快照"
        # 新的: "X天前数据", "最新快照"
        # 注意"最新快照"新旧都有，所以用其他特征区分
        # 旧的只有3种备注: "14天前快照", "7天前快照", "最新快照"
        if remark in ["14天前快照", "7天前快照", "最新快照"]:
            old_ids.append(s["_record_id"])
        else:
            new_ids.append(s["_record_id"])
    
    print(f"旧快照（规整的）: {len(old_ids)} 条")
    print(f"新快照（自然的）: {len(new_ids)} 条")
    
    if old_ids:
        print(f"\n删除旧快照...")
        # 分批删，每批30条
        deleted = 0
        for i in range(0, len(old_ids), 30):
            batch = old_ids[i:i+30]
            d = delete_batch(config, snapshot_table, batch)
            deleted += d
            print(f"  批次 {i//30+1}: 删除 {len(batch)} 条")
            time.sleep(0.5)
        
        print(f"共删除: {deleted} 条")
    
    # 验证剩余数量
    remaining = list_records(config, snapshot_table, ["备注"])
    print(f"\n剩余快照: {len(remaining)} 条")


if __name__ == "__main__":
    main()
