"""获取视图列表并设置各平台筛选条件"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark


def get_views(config, table_id):
    """获取表的所有视图"""
    data = run_lark(config, [
        "+view-list",
        "--as", "user",
        "--base-token", config["base_token"],
        "--table-id", table_id,
    ], timeout=30)
    return data.get("data", {}).get("views", [])


def set_view_filter(config, table_id, view_id, filter_json):
    """设置视图筛选条件"""
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    pf = tmp / f"view_filter_{view_id}.json"
    pf.write_text(json.dumps(filter_json), encoding="utf-8")
    
    try:
        run_lark(config, [
            "+view-set-filter",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--view-id", view_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        print(f"    ✅ 筛选条件已设置")
        return True
    except Exception as e:
        print(f"    ❌ 筛选设置失败: {e}")
        return False
    finally:
        pf.unlink(missing_ok=True)


def main():
    config = load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    videos_table = config["tables"]["videos"]["table_id"]
    
    # ========== 博主表视图 ==========
    print("\n=== 博主表视图 ===")
    creator_views = get_views(config, creators_table)
    for v in creator_views:
        print(f"  {v['name']} ({v['id']}) - {v['type']}")
    
    # 设置博主表各平台筛选
    creator_filters = {
        "B站博主": {
            "logic": "or",
            "conditions": [
                ["B站MID", "!=", ""],
            ]
        },
        "抖音博主": {
            "logic": "or",
            "conditions": [
                ["抖音SecUID", "!=", ""],
            ]
        },
        "小红书博主": {
            "logic": "or",
            "conditions": [
                ["小红书用户ID", "!=", ""],
            ]
        },
        "快手博主": {
            "logic": "or",
            "conditions": [
                ["快手用户ID", "!=", ""],
            ]
        },
    }
    
    for v in creator_views:
        if v["name"] in creator_filters:
            print(f"\n设置筛选: {v['name']}")
            set_view_filter(config, creators_table, v["id"], creator_filters[v["name"]])
    
    # ========== 视频表视图 ==========
    print("\n=== 视频表视图 ===")
    video_views = get_views(config, videos_table)
    for v in video_views:
        print(f"  {v['name']} ({v['id']}) - {v['type']}")
    
    # 设置视频表各平台筛选
    video_filters = {
        "B站封面": {"平台": "B站"},
        "抖音封面": {"平台": "抖音"},
        "小红书封面": {"平台": "小红书"},
        "快手封面": {"平台": "快手"},
    }
    
    for v in video_views:
        if v["name"] in video_filters:
            platform = video_filters[v["name"]]["平台"]
            print(f"\n设置筛选: {v['name']} (平台={platform})")
            filter_cfg = {
                "logic": "and",
                "conditions": [
                    ["平台", "==", platform]
                ]
            }
            set_view_filter(config, videos_table, v["id"], filter_cfg)
    
    print("\n✅ 全部视图筛选设置完成")


if __name__ == "__main__":
    main()
