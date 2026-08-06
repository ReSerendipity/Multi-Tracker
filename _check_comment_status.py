"""检查评论抓取状态字段真实值"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records

def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    
    fields = ["视频标题", "BVID", "平台", "评论抓取状态", "已抓评论数"]
    rows = list_records(config, videos_table, fields)
    bili_videos = [r for r in rows if r.get("平台") == "B站"]
    
    print(f"B站视频: {len(bili_videos)}")
    
    # 统计状态分布
    status_counts = {}
    for r in bili_videos:
        status = str(r.get("评论抓取状态", "空"))
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("状态分布:")
    for s, c in status_counts.items():
        print(f"  {s}: {c}")
    
    # 看看前5个的具体值
    print("\n前5个视频:")
    for r in bili_videos[:5]:
        print(f"  {str(r.get('视频标题',''))[:30]} | 状态={r.get('评论抓取状态')} | 数量={r.get('已抓评论数')}")


if __name__ == "__main__":
    main()
