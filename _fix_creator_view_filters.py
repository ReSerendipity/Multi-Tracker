"""只设置博主表的视图筛选"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark


def get_views(config, table_id):
    data = run_lark(config, [
        "+view-list", "--as", "user",
        "--base-token", config["base_token"],
        "--table-id", table_id,
    ], timeout=30)
    return data.get("data", {}).get("views", [])


def set_view_filter(config, table_id, view_id, filter_cfg):
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"vf_{view_id}.json"
    pf.write_text(json.dumps(filter_cfg), encoding="utf-8")
    try:
        run_lark(config, [
            "+view-set-filter", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--view-id", view_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        print(f"  ✅ OK")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False
    finally:
        pf.unlink(missing_ok=True)


def main():
    config = load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    
    views = get_views(config, creators_table)
    print("博主表视图:")
    for v in views:
        print(f"  {v['name']} ({v['id']})")
    
    filters = {
        "B站博主": {"logic": "or", "conditions": [["B站MID", "non_empty", ""]]},
        "抖音博主": {"logic": "or", "conditions": [["抖音SecUID", "non_empty", ""]]},
        "小红书博主": {"logic": "or", "conditions": [["小红书用户ID", "non_empty", ""]]},
        "快手博主": {"logic": "or", "conditions": [["快手用户ID", "non_empty", ""]]},
    }
    
    for v in views:
        if v["name"] in filters:
            print(f"\n设置: {v['name']}")
            set_view_filter(config, creators_table, v["id"], filters[v["name"]])
    
    print("\n完成!")


if __name__ == "__main__":
    main()
