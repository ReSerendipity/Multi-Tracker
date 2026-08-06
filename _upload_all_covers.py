"""批量上传视频封面到飞书"""
import sys, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark

def upload_cover(config, table_id, record_id, cover_path, field_name="封面"):
    """上传封面到指定记录的附件字段"""
    # 必须用相对路径
    rel_path = cover_path.relative_to(ROOT)
    
    args = [
        "+record-upload-attachment",
        "--as", "user",
        "--base-token", config["base_token"],
        "--table-id", table_id,
        "--record-id", record_id,
        "--field-id", field_name,
        "--file", str(rel_path),
    ]
    
    try:
        data = run_lark(config, args, timeout=60)
        return True
    except Exception as e:
        print(f"    上传失败: {e}")
        return False


def main():
    config = load_config()
    table_id = config["tables"]["videos"]["table_id"]
    
    # 读取所有视频
    fields = ["视频标题", "平台", "BVID", "平台视频ID", "封面", "封面文件路径"]
    rows = list_records(config, table_id, fields)
    
    print(f"总视频数: {len(rows)}")
    
    # 找出没有封面但有封面文件路径的
    to_upload = []
    for row in rows:
        has_cover = bool(row.get("封面"))
        cover_path_str = row.get("封面文件路径", "") or ""
        
        if not has_cover and cover_path_str:
            cover_path = Path(cover_path_str)
            if cover_path.exists():
                to_upload.append({
                    "record_id": row["_record_id"],
                    "title": row.get("视频标题", "")[:40],
                    "platform": row.get("平台", ""),
                    "cover_path": cover_path,
                })
    
    print(f"需要上传封面的视频: {len(to_upload)} 个")
    
    success = 0
    for i, item in enumerate(to_upload):
        print(f"[{i+1}/{len(to_upload)}] [{item['platform']}] {item['title']}")
        
        ok = upload_cover(config, table_id, item["record_id"], item["cover_path"])
        if ok:
            success += 1
            print(f"  ✅ 上传成功")
        else:
            print(f"  ❌ 上传失败")
        
        # 稍微限速
        time.sleep(0.5)
    
    print(f"\n完成! 成功上传 {success}/{len(to_upload)} 个封面")


if __name__ == "__main__":
    main()
