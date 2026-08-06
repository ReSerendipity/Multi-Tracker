"""检查博主表和各表现状"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, field_names, list_records

def main():
    config = load_config()
    
    # 博主表
    creators_table = config["tables"]["creators"]["table_id"]
    creator_fields = field_names(config, creators_table)
    print("=== 博主表字段 ===")
    for name, info in creator_fields.items():
        print(f"  {name}: {info['type']}")
    
    creator_rows = list_records(config, creators_table, list(creator_fields.keys()))
    print(f"\n博主总数: {len(creator_rows)}")
    for r in creator_rows:
        name = r.get("博主名称", "未知")
        platform = r.get("平台", "")
        mid = r.get("B站MID", "") or ""
        secuid = r.get("抖音SecUID", "") or ""
        tracking = r.get("是否持续跟踪", False)
        print(f"  {name} | 平台:{platform} | B站:{mid[:15]} | 抖音:{secuid[:15]} | 跟踪:{tracking}")
    
    # 视频表统计
    videos_table = config["tables"]["videos"]["table_id"]
    video_rows = list_records(config, videos_table, ["视频标题", "平台", "封面", "视频下载状态", "评论抓取状态", "已抓评论数", "时长秒", "发布时间"])
    
    print(f"\n=== 视频表统计 ===")
    print(f"总视频数: {len(video_rows)}")
    
    by_platform = {}
    for r in video_rows:
        p = str(r.get("平台", "未知"))
        if p not in by_platform:
            by_platform[p] = {"count": 0, "with_cover": 0, "downloaded": 0}
        by_platform[p]["count"] += 1
        if r.get("封面"):
            by_platform[p]["with_cover"] += 1
        if r.get("视频下载状态") == "已下载":
            by_platform[p]["downloaded"] += 1
    
    for p, stats in by_platform.items():
        print(f"  {p}: {stats['count']}条 | 有封面:{stats['with_cover']} | 已下载:{stats['downloaded']}")


if __name__ == "__main__":
    main()
