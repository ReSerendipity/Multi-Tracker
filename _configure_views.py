"""
配置各平台视图：
1. 博主表4个视图：只显示对应平台的相关字段
2. 快照表：按时间倒序排列，添加视频标题lookup
"""
import sys, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark, field_names


def set_visible_fields(config, table_id, view_id, field_names_list):
    """设置视图可见字段"""
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"vf_{view_id}.json"
    pf.write_text(json.dumps({"visible_fields": field_names_list}), encoding="utf-8")
    
    try:
        run_lark(config, [
            "+view-set-visible-fields",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--view-id", view_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=20)
        pf.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"  失败: {e}")
        pf.unlink(missing_ok=True)
        return False


def set_view_sort(config, table_id, view_id, sort_rules):
    """设置视图排序
    sort_rules: [{"field": "字段名", "desc": True}]
    """
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"sort_{view_id}.json"
    pf.write_text(json.dumps({"sort_config": sort_rules}), encoding="utf-8")
    
    try:
        run_lark(config, [
            "+view-set-sort",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--view-id", view_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=20)
        pf.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"  失败: {e}")
        pf.unlink(missing_ok=True)
        return False


def create_lookup_field(config, table_id, field_name, link_field, target_field):
    """创建lookup字段"""
    field_config = {
        "field_name": field_name,
        "type": "lookup",
        "property": {
            "table_id": "",  # 自动从link字段推断
            "link_field": link_field,
            "target_field": target_field,
            "rollup_type": "none",
        }
    }
    
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"lookup_{field_name}.json"
    pf.write_text(json.dumps(field_config), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+field-create",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{pf.relative_to(ROOT)}",
            "--i-have-read-guide",
        ], timeout=20)
        pf.unlink(missing_ok=True)
        print(f"  ✅ 创建lookup字段: {field_name}")
        return True
    except Exception as e:
        print(f"  ❌ 创建失败: {e}")
        pf.unlink(missing_ok=True)
        return False


def main():
    config = load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    videos_table = config["tables"]["videos"]["table_id"]
    
    # ========== 博主表视图字段 ==========
    print("\n=== 配置博主表视图字段 ===")
    
    # 获取所有视图ID
    views_data = run_lark(config, [
        "+view-list", "--as", "user",
        "--base-token", config["base_token"],
        "--table-id", creators_table,
    ], timeout=15)
    views = views_data.get("data", {}).get("views", [])
    view_map = {v["name"]: v["id"] for v in views}
    
    # B站博主视图：只显示B站相关字段
    bili_fields = ["博主名称", "B站MID", "主页链接", "平台", "是否持续跟踪", "最近采集时间"]
    bili_view_id = view_map.get("B站博主")
    if bili_view_id:
        print(f"配置 B站博主 视图字段 ({len(bili_fields)}个)...")
        set_visible_fields(config, creators_table, bili_view_id, bili_fields)
    
    # 抖音博主视图
    douyin_fields = ["博主名称", "抖音SecUID", "抖音主页链接", "平台", "是否持续跟踪", "抖音持续跟踪", "最近采集时间"]
    dy_view_id = view_map.get("抖音博主")
    if dy_view_id:
        print(f"配置 抖音博主 视图字段 ({len(douyin_fields)}个)...")
        set_visible_fields(config, creators_table, dy_view_id, douyin_fields)
    
    # 小红书博主视图
    xhs_fields = ["博主名称", "小红书用户ID", "小红书主页链接", "平台", "是否持续跟踪", "小红书持续跟踪", "最近采集时间"]
    xhs_view_id = view_map.get("小红书博主")
    if xhs_view_id:
        print(f"配置 小红书博主 视图字段 ({len(xhs_fields)}个)...")
        set_visible_fields(config, creators_table, xhs_view_id, xhs_fields)
    
    # 快手博主视图
    ks_fields = ["博主名称", "快手用户ID", "快手主页链接", "平台", "是否持续跟踪", "快手持续跟踪", "最近采集时间"]
    ks_view_id = view_map.get("快手博主")
    if ks_view_id:
        print(f"配置 快手博主 视图字段 ({len(ks_fields)}个)...")
        set_visible_fields(config, creators_table, ks_view_id, ks_fields)
    
    # ========== 快照表：添加视频标题 + 按时间排序 ==========
    print("\n=== 配置快照表 ===")
    
    # 检查是否已有视频标题lookup字段
    snap_fields = field_names(config, snapshot_table)
    print(f"快照表现有字段: {list(snap_fields.keys())}")
    
    if "视频标题" not in snap_fields:
        print("创建视频标题 lookup 字段...")
        # 先试试创建lookup
        try:
            create_lookup_field(config, snapshot_table, "视频标题", "关联视频", "视频标题")
        except Exception as e:
            print(f"  lookup创建有问题: {e}")
    else:
        print("视频标题字段已存在")
    
    # 获取快照表视图
    snap_views_data = run_lark(config, [
        "+view-list", "--as", "user",
        "--base-token", config["base_token"],
        "--table-id", snapshot_table,
    ], timeout=15)
    snap_views = snap_views_data.get("data", {}).get("views", [])
    snap_view_map = {v["name"]: v["id"] for v in snap_views}
    
    print(f"快照表视图: {list(snap_view_map.keys())}")
    
    # 给默认视图设置按快照时间倒序
    default_view = snap_views[0]["id"] if snap_views else None
    if default_view:
        print(f"设置快照按时间倒序...")
        set_view_sort(config, snapshot_table, default_view, [{"field": "快照时间", "desc": True}])
    
    # 设置快照表可见字段（包含视频标题）
    visible_snap_fields = ["视频标题", "快照时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数", "粉丝数快照", "备注"]
    if default_view:
        print(f"设置快照表可见字段 ({len(visible_snap_fields)}个)...")
        set_visible_fields(config, snapshot_table, default_view, visible_snap_fields)
    
    print("\n✅ 全部配置完成!")


if __name__ == "__main__":
    main()
