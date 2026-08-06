"""创建各平台筛选视图"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark


def create_view(config, table_id, name, view_type="grid"):
    """创建一个新视图"""
    import tempfile
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    view_config = {"name": name, "type": view_type}
    pf = tmp / f"create_view_{name}.json"
    pf.write_text(json.dumps(view_config), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+view-create",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        view_id = data.get("data", {}).get("view_id")
        print(f"  ✅ 创建视图: {name} ({view_id})")
        pf.unlink(missing_ok=True)
        return view_id
    except Exception as e:
        print(f"  ❌ 创建失败: {e}")
        pf.unlink(missing_ok=True)
        return None


def set_view_filter(config, table_id, view_id, filter_json):
    """设置视图筛选条件"""
    import tempfile
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


def set_gallery_cover(config, table_id, view_id, cover_field_id):
    """设置画册视图的封面字段 - 通过view-update"""
    # 先获取当前视图配置
    try:
        data = run_lark(config, [
            "+view-get",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--view-id", view_id,
        ], timeout=30)
        print(f"  视图配置: {json.dumps(data.get('data', {}), ensure_ascii=False)[:200]}")
        return True
    except Exception as e:
        print(f"  获取视图失败: {e}")
        return False


def main():
    config = load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    videos_table = config["tables"]["videos"]["table_id"]
    
    # ========== 博主表视图 ==========
    print("\n=== 创建博主表平台视图 ===")
    
    # B站视图
    bili_view_id = create_view(config, creators_table, "B站博主", "grid")
    if bili_view_id:
        # 筛选：B站MID不为空 或者 平台包含B站
        filter_bili = {
            "conjunction": "or",
            "conditions": [
                {
                    "field_id": "B站MID",
                    "operator": "isNotEmpty",
                    "value": []
                },
                {
                    "field_id": "平台",
                    "operator": "contains",
                    "value": ["B站"]
                }
            ]
        }
        set_view_filter(config, creators_table, bili_view_id, filter_bili)
    
    # 抖音视图
    douyin_view_id = create_view(config, creators_table, "抖音博主", "grid")
    if douyin_view_id:
        filter_douyin = {
            "conjunction": "or",
            "conditions": [
                {
                    "field_id": "抖音SecUID",
                    "operator": "isNotEmpty",
                    "value": []
                },
                {
                    "field_id": "平台",
                    "operator": "contains",
                    "value": ["抖音"]
                }
            ]
        }
        set_view_filter(config, creators_table, douyin_view_id, filter_douyin)
    
    # 小红书视图
    xhs_view_id = create_view(config, creators_table, "小红书博主", "grid")
    if xhs_view_id:
        filter_xhs = {
            "conjunction": "or",
            "conditions": [
                {
                    "field_id": "小红书用户ID",
                    "operator": "isNotEmpty",
                    "value": []
                },
                {
                    "field_id": "平台",
                    "operator": "contains",
                    "value": ["小红书"]
                }
            ]
        }
        set_view_filter(config, creators_table, xhs_view_id, filter_xhs)
    
    # 快手视图
    ks_view_id = create_view(config, creators_table, "快手博主", "grid")
    if ks_view_id:
        filter_ks = {
            "conjunction": "or",
            "conditions": [
                {
                    "field_id": "快手用户ID",
                    "operator": "isNotEmpty",
                    "value": []
                },
                {
                    "field_id": "平台",
                    "operator": "contains",
                    "value": ["快手"]
                }
            ]
        }
        set_view_filter(config, creators_table, ks_view_id, filter_ks)
    
    # ========== 视频表封面视图 ==========
    print("\n=== 创建视频表平台封面视图 ===")
    
    platforms = [
        ("B站封面", "B站"),
        ("抖音封面", "抖音"),
        ("小红书封面", "小红书"),
        ("快手封面", "快手"),
    ]
    
    for view_name, platform in platforms:
        view_id = create_view(config, videos_table, view_name, "gallery")
        if view_id:
            filter_platform = {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_id": "平台",
                        "operator": "is",
                        "value": [platform]
                    }
                ]
            }
            set_view_filter(config, videos_table, view_id, filter_platform)
    
    print("\n✅ 全部视图创建完成")


if __name__ == "__main__":
    main()
