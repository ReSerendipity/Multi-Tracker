"""检查飞书视频表现状和可用封面文件"""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, field_names, list_records

def main():
    config = load_config()
    table_id = config["tables"]["videos"]["table_id"]
    
    # 列出所有字段
    fields = field_names(config, table_id)
    print("视频表字段:")
    for name, info in fields.items():
        print(f"  {name}: {info['type']}")
    
    # 读取所有视频记录
    video_fields = ["视频标题", "平台", "平台视频ID", "BVID", "封面", "封面文件路径", "视频下载状态", "关联博主"]
    rows = list_records(config, table_id, video_fields)
    
    print(f"\n总视频数: {len(rows)}")
    
    # 按平台分类统计
    by_platform = {}
    for row in rows:
        platform = str(row.get("平台", "未知"))
        if platform not in by_platform:
            by_platform[platform] = []
        by_platform[platform].append(row)
    
    print("\n按平台分布:")
    for plat, items in by_platform.items():
        has_cover = sum(1 for r in items if r.get("封面"))
        no_cover = sum(1 for r in items if not r.get("封面"))
        print(f"  {plat}: {len(items)} 条 (有封面: {has_cover}, 无封面: {no_cover})")
    
    # 看看哪些没有封面
    print("\n无封面的视频:")
    for row in rows:
        if not row.get("封面"):
            cover_path = row.get("封面文件路径", "")
            title = row.get("视频标题", "")[:40]
            platform = row.get("平台", "")
            print(f"  [{platform}] {title}")
            print(f"    封面路径: {cover_path}")
            print(f"    record_id: {row.get('record_id', '')}")
    
    # 检查本地封面文件
    print("\n本地封面文件:")
    downloads = ROOT / "downloads"
    if downloads.exists():
        for p in downloads.rglob("*.jpg"):
            if "cover" in p.name or "封面" in p.name:
                size_kb = p.stat().st_size / 1024
                print(f"  {p.relative_to(ROOT)} ({size_kb:.0f} KB)")
        
        for p in downloads.rglob("*.png"):
            if "cover" in p.name or "封面" in p.name:
                size_kb = p.stat().st_size / 1024
                print(f"  {p.relative_to(ROOT)} ({size_kb:.0f} KB)")

if __name__ == "__main__":
    main()
