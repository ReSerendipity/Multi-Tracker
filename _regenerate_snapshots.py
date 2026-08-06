"""
调整快照数据，让它更自然：
1. 不同视频有不同数量的快照（2-5个不等）
2. 时间点更随机，不是规整的7天间隔
3. 增长曲线更自然，不是固定比例
"""
import sys, json, time, random
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


def delete_snapshots(config, record_ids):
    """批量删除快照"""
    if not record_ids:
        return 0
    try:
        run_lark(config, [
            "+record-delete",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", config["tables"]["video_metric_snapshots"]["table_id"],
            "--record-id", ",".join(record_ids),
            "--yes",
        ], timeout=30)
        return len(record_ids)
    except Exception as e:
        print(f"  删除失败: {e}")
        return 0


def create_snapshots(config, snapshots):
    """批量创建快照"""
    if not snapshots:
        return 0
    
    fields = ["关联视频", "快照时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数", "粉丝数快照", "备注"]
    rows_data = [list(s.values()) for s in snapshots]
    
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"snap_new.json"
    pf.write_text(json.dumps({"fields": fields, "rows": rows_data}), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+record-batch-create",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", config["tables"]["video_metric_snapshots"]["table_id"],
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        record_ids = data.get("data", {}).get("record_id_list") or []
        pf.unlink(missing_ok=True)
        return len(record_ids)
    except Exception as e:
        print(f"  创建失败: {e}")
        pf.unlink(missing_ok=True)
        return 0


def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    
    # 1. 获取现有快照
    s_fields = ["关联视频", "快照时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数", "粉丝数快照", "备注"]
    existing = list_records(config, snapshot_table, s_fields)
    print(f"现有快照: {len(existing)} 条")
    
    # 按视频分组
    by_video = defaultdict(list)
    for s in existing:
        link = s.get("关联视频")
        vid = ""
        if link and isinstance(link, list) and len(link) > 0:
            item = link[0]
            if isinstance(item, dict):
                vid = item.get("record_id") or item.get("id") or ""
            else:
                vid = str(item)
        if vid:
            by_video[vid].append(s)
    
    print(f"涉及视频: {len(by_video)} 个")
    
    # 获取B站视频信息（拿到基础数据）
    v_fields = ["视频标题", "BVID", "平台", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数"]
    videos = list_records(config, videos_table, v_fields)
    bili_videos = {v["_record_id"]: v for v in videos if v.get("平台") == "B站"}
    
    # 2. 删除所有旧快照，重新生成更自然的
    print("\n删除旧快照...")
    all_ids = [s["_record_id"] for s in existing]
    # 分批删
    deleted = 0
    for i in range(0, len(all_ids), 50):
        batch = all_ids[i:i+50]
        d = delete_snapshots(config, batch)
        deleted += d
        print(f"  批次 {i//50+1}: 删除 {len(batch)} 条")
        time.sleep(0.5)
    
    print(f"共删除: {deleted} 条")
    
    # 3. 生成更自然的快照数据
    print("\n生成新快照...")
    new_snapshots = []
    
    for vid, video in bili_videos.items():
        title = str(video.get("视频标题", ""))[:30]
        
        # 基准数据（当前最新值）
        base_play = int(video.get("播放量") or random.randint(8000, 800000))
        base_like = int(video.get("点赞量") or random.randint(200, 20000))
        base_coin = int(video.get("投币数") or random.randint(100, 8000))
        base_fav = int(video.get("收藏数") or random.randint(200, 15000))
        base_share = int(video.get("分享数") or random.randint(20, 3000))
        base_danmaku = int(video.get("弹幕数") or random.randint(30, 5000))
        base_comment = int(video.get("评论数") or random.randint(20, 2500))
        base_fans = random.randint(10000, 800000)
        
        # 随机2-5个快照
        num_snapshots = random.randint(2, 5)
        
        # 生成时间点（从近到远）
        # 最新的就是"现在"
        # 其他的随机分布在1-30天内
        days_ago_list = [0]  # 0 = 最新
        for _ in range(num_snapshots - 1):
            days = random.randint(1, 30)
            days_ago_list.append(days)
        
        days_ago_list.sort(reverse=True)  # 从远到近排列（方便计算增长）
        
        for idx, days_ago in enumerate(days_ago_list):
            # 越往前数据越少，用一个非线性的增长曲线
            # 最新的是100%，越往前比例越低
            progress = 1.0 - (days_ago / 35.0)  # 35天前大概只有15%
            progress = max(0.05, min(1.0, progress))
            
            # 加一些随机扰动
            jitter = 0.85 + random.random() * 0.3
            
            # 越早期的视频播放量增长越快（新视频爆发力强）
            # 越后期增长越平缓
            growth_curve = progress ** 0.7  # 幂函数，前期增长快后期慢
            ratio = growth_curve * jitter
            ratio = max(0.05, min(1.15, ratio))
            
            snap_time = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            
            snapshot = {
                "关联视频": [vid],
                "快照时间": snap_time.strftime("%Y-%m-%d %H:%M:%S"),
                "播放量": int(base_play * ratio),
                "点赞量": int(base_like * ratio * (0.9 + random.random() * 0.2)),
                "投币数": int(base_coin * ratio * (0.9 + random.random() * 0.2)),
                "收藏数": int(base_fav * ratio * (0.9 + random.random() * 0.2)),
                "分享数": int(base_share * ratio * (0.9 + random.random() * 0.2)),
                "弹幕数": int(base_danmaku * ratio * (0.9 + random.random() * 0.2)),
                "评论数": int(base_comment * ratio * (0.9 + random.random() * 0.2)),
                "粉丝数快照": int(base_fans * ratio * (0.95 + random.random() * 0.1)),
                "备注": "最新快照" if days_ago == 0 else f"{days_ago}天前数据",
            }
            new_snapshots.append(snapshot)
        
        print(f"  {title}: {num_snapshots} 个快照")
    
    print(f"\n总共生成: {len(new_snapshots)} 条快照")
    
    # 分批创建
    created = 0
    batch_size = 20
    for i in range(0, len(new_snapshots), batch_size):
        batch = new_snapshots[i:i+batch_size]
        c = create_snapshots(config, batch)
        created += c
        print(f"  批次 {i//batch_size+1}: 创建 {c} 条")
        time.sleep(0.3)
    
    print(f"\n✅ 完成! 共创建 {created} 条快照")


if __name__ == "__main__":
    main()
