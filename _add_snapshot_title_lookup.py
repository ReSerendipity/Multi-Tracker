"""在快照表创建视频标题lookup字段，并更新可见字段"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark


def main():
    config = load_config()
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    
    # 创建视频标题 lookup 字段
    lookup_config = {
        "name": "视频标题",
        "type": "lookup",
        "from": "视频",
        "select": "视频标题",
        "where": {
            "logic": "and",
            "conditions": [
                ["记录ID", "intersects", {"type": "field_ref", "field": "关联视频"}]
            ]
        },
        "aggregate": "raw_value",
    }
    
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / "lookup_vtitle.json"
    pf.write_text(json.dumps(lookup_config), encoding="utf-8")
    
    print("创建视频标题 lookup 字段...")
    try:
        data = run_lark(config, [
            "+field-create", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", snapshot_table,
            "--json", f"@{pf.relative_to(ROOT)}",
            "--i-have-read-guide",
        ], timeout=20)
        print(f"  ✅ 成功! field_id: {data.get('data', {}).get('field_id', '')}")
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        pf.unlink(missing_ok=True)
        return
    
    pf.unlink(missing_ok=True)
    
    # 更新视图可见字段，把视频标题放在最前面
    print("\n更新视图可见字段...")
    visible_fields = ["视频标题", "快照时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数", "粉丝数快照", "备注"]
    
    pf2 = tmp / "vf_snap.json"
    pf2.write_text(json.dumps({"visible_fields": visible_fields}), encoding="utf-8")
    
    try:
        run_lark(config, [
            "+view-set-visible-fields", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", snapshot_table,
            "--view-id", "Grid View",
            "--json", f"@{pf2.relative_to(ROOT)}",
        ], timeout=20)
        print(f"  ✅ 成功!")
    except Exception as e:
        print(f"  ❌ 失败: {e}")
    finally:
        pf2.unlink(missing_ok=True)
    
    print("\n完成!")


if __name__ == "__main__":
    main()
