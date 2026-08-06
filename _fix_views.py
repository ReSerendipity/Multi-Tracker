"""修复视图配置"""
import sys, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, run_lark


def set_visible_fields(config, table_id, view_id, field_names_list):
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"vf_{view_id}.json"
    pf.write_text(json.dumps({"visible_fields": field_names_list}), encoding="utf-8")
    try:
        run_lark(config, [
            "+view-set-visible-fields", "--as", "user",
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


def main():
    config = load_config()
    creators_table = config["tables"]["creators"]["table_id"]
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    
    # 1. 重试小红书博主视图
    print("重试小红书博主视图字段...")
    time.sleep(2)
    xhs_fields = ["博主名称", "小红书用户ID", "小红书主页链接", "平台", "是否持续跟踪", "小红书持续跟踪", "最近采集时间"]
    ok = set_visible_fields(config, creators_table, "小红书博主", xhs_fields)
    if ok:
        print("  ✅ 成功")
    else:
        print("  ❌ 失败")
    
    # 2. 快照表可见字段（去掉不存在的视频标题）
    print("\n设置快照表可见字段...")
    snap_fields = ["关联视频", "快照时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数", "粉丝数快照", "备注"]
    ok = set_visible_fields(config, snapshot_table, "Grid View", snap_fields)
    if ok:
        print("  ✅ 成功")
    else:
        print("  ❌ 失败")
    
    print("\n完成!")


if __name__ == "__main__":
    main()
