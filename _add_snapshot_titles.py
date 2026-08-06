"""
给快照表加视频标题字段，并填充数据
"""
import sys, json, time
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    
    # 1. 创建视频标题字段
    print("创建视频标题字段...")
    field_config = {
        "name": "视频标题",
        "type": "text",
    }
    
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / "field_vtitle.json"
    pf.write_text(json.dumps(field_config), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+field-create", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", snapshot_table,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=20)
        print(f"  ✅ 成功")
    except Exception as e:
        if "already exists" in str(e) or "字段已存在" in str(e):
            print(f"  ⚠️  字段已存在")
        else:
            print(f"  ❌ 失败: {e}")
    pf.unlink(missing_ok=True)
    
    # 2. 获取所有视频的ID和标题映射
    print("\n获取视频标题映射...")
    v_fields = ["视频标题", "BVID"]
    videos = list_records(config, videos_table, v_fields)
    vid_to_title = {v["_record_id"]: v.get("视频标题", "") for v in videos}
    print(f"  共 {len(vid_to_title)} 个视频")
    
    # 3. 获取所有快照
    s_fields = ["关联视频", "视频标题"]
    snapshots = list_records(config, snapshot_table, s_fields)
    print(f"  共 {len(snapshots)} 条快照")
    
    # 4. 为没有标题的快照填充标题
    to_update = []
    for s in snapshots:
        if s.get("视频标题"):
            continue
        
        link = s.get("关联视频")
        vid = ""
        if link and isinstance(link, list) and len(link) > 0:
            item = link[0]
            if isinstance(item, dict):
                vid = item.get("id") or item.get("record_id") or ""
            else:
                vid = str(item)
        
        if vid and vid in vid_to_title:
            to_update.append({
                "record_id": s["_record_id"],
                "title": vid_to_title[vid],
            })
    
    print(f"\n需要填充标题: {len(to_update)} 条")
    
    # 批量更新（用batch-update但每条值不同，所以只能逐条或分批用相同值...不对，batch-update是同值更新多条）
    # 用 upsert 逐条更新
    success = 0
    for i, item in enumerate(to_update):
        try:
            pf2 = tmp / f"upd_{i}.json"
            pf2.write_text(json.dumps({"视频标题": item["title"]}), encoding="utf-8")
            
            run_lark(config, [
                "+record-upsert", "--as", "user",
                "--base-token", config["base_token"],
                "--table-id", snapshot_table,
                "--record-id", item["record_id"],
                "--json", f"@{pf2.relative_to(ROOT)}",
            ], timeout=15)
            pf2.unlink(missing_ok=True)
            success += 1
        except Exception as e:
            print(f"  更新失败: {e}")
        
        if (i+1) % 20 == 0:
            print(f"  进度: {i+1}/{len(to_update)}")
    
    print(f"\n✅ 填充完成: {success}/{len(to_update)}")
    
    # 5. 更新视图可见字段，把视频标题放在最前面
    print("\n更新视图可见字段...")
    visible_fields = ["视频标题", "快照时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数", "粉丝数快照", "备注"]
    
    pf3 = tmp / "vf_snap.json"
    pf3.write_text(json.dumps({"visible_fields": visible_fields}), encoding="utf-8")
    
    try:
        run_lark(config, [
            "+view-set-visible-fields", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", snapshot_table,
            "--view-id", "Grid View",
            "--json", f"@{pf3.relative_to(ROOT)}",
        ], timeout=20)
        print(f"  ✅ 成功!")
    except Exception as e:
        print(f"  ❌ 失败: {e}")
    finally:
        pf3.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
