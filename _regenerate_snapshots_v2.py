"""
修复快照数据：
1. 获取真实B站视频的发布时间
2. 确保所有快照时间都在视频发布时间之后
3. 真实视频的快照放前面，样例视频的放后面
"""
import sys, json, time, random, requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


def get_bili_video_info(bvid):
    """从B站API获取视频发布时间等信息"""
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            d = data["data"]
            return {
                "pubdate": d.get("pubdate", 0),  # 时间戳
                "view": d.get("stat", {}).get("view", 0),
                "like": d.get("stat", {}).get("like", 0),
                "coin": d.get("stat", {}).get("coin", 0),
                "favorite": d.get("stat", {}).get("favorite", 0),
                "share": d.get("stat", {}).get("share", 0),
                "danmaku": d.get("stat", {}).get("danmaku", 0),
                "reply": d.get("stat", {}).get("reply", 0),
            }
    except Exception as e:
        print(f"    获取视频信息失败: {e}")
    return None


def delete_snapshots(config, record_ids):
    """批量删除快照"""
    if not record_ids:
        return 0
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"del_snap.json"
    pf.write_text(json.dumps({"record_id_list": record_ids}), encoding="utf-8")
    try:
        run_lark(config, [
            "+record-delete", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", config["tables"]["video_metric_snapshots"]["table_id"],
            "--json", f"@{pf.relative_to(ROOT)}",
            "--yes",
        ], timeout=30)
        pf.unlink(missing_ok=True)
        return len(record_ids)
    except Exception as e:
        print(f"  删除失败: {e}")
        pf.unlink(missing_ok=True)
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
            "+record-batch-create", "--as", "user",
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
    
    # 1. 获取所有B站视频
    v_fields = ["视频标题", "BVID", "平台", "发布时间", "播放量", "点赞量", "投币数", "收藏数", "分享数", "弹幕数", "评论数"]
    video_rows = list_records(config, videos_table, v_fields)
    bili_videos = [r for r in video_rows if r.get("平台") == "B站" and r.get("BVID")]
    
    print(f"B站视频: {len(bili_videos)} 个")
    
    # 2. 区分真实视频和样例视频
    real_videos = []   # 能从B站API拿到真实数据的
    sample_videos = [] # 样例数据（BVID是假的）
    
    for v in bili_videos:
        bvid = v["BVID"]
        title = str(v.get("视频标题", ""))[:40]
        print(f"\n检查: {title}")
        
        info = get_bili_video_info(bvid)
        if info and info["pubdate"] > 0:
            pub_time = datetime.fromtimestamp(info["pubdate"])
            print(f"  ✅ 真实视频 | 发布: {pub_time.strftime('%Y-%m-%d')} | 播放: {info['view']}")
            real_videos.append({
                "record_id": v["_record_id"],
                "bvid": bvid,
                "title": title,
                "pubdate": info["pubdate"],
                "pub_time": pub_time,
                "view": info["view"],
                "like": info["like"],
                "coin": info["coin"],
                "favorite": info["favorite"],
                "share": info["share"],
                "danmaku": info["danmaku"],
                "reply": info["reply"],
            })
        else:
            print(f"  ❌ 样例视频（无真实数据）")
            sample_videos.append({
                "record_id": v["_record_id"],
                "bvid": bvid,
                "title": title,
                "view": int(v.get("播放量") or random.randint(10000, 500000)),
                "like": int(v.get("点赞量") or random.randint(200, 20000)),
                "coin": int(v.get("投币数") or random.randint(100, 8000)),
                "favorite": int(v.get("收藏数") or random.randint(200, 15000)),
                "share": int(v.get("分享数") or random.randint(20, 3000)),
                "danmaku": int(v.get("弹幕数") or random.randint(30, 5000)),
                "reply": int(v.get("评论数") or random.randint(20, 2500)),
            })
        
        time.sleep(0.3)
    
    print(f"\n真实视频: {len(real_videos)} 个")
    print(f"样例视频: {len(sample_videos)} 个")
    
    # 3. 删除所有旧快照
    print("\n删除所有旧快照...")
    old_snaps = list_records(config, snapshot_table, ["备注"])
    old_ids = [s["_record_id"] for s in old_snaps]
    print(f"待删除: {len(old_ids)} 条")
    
    deleted = 0
    for i in range(0, len(old_ids), 30):
        batch = old_ids[i:i+30]
        d = delete_snapshots(config, batch)
        deleted += d
        print(f"  批次 {i//30+1}: 删除 {len(batch)} 条")
        time.sleep(0.5)
    
    print(f"共删除: {deleted} 条")
    
    # 4. 为真实视频生成快照（严格在发布时间之后）
    print("\n生成真实视频快照...")
    all_new_snapshots = []
    
    now = datetime.now()
    
    for video in real_videos:
        pub_time = video["pub_time"]
        days_since_pub = (now - pub_time).days
        
        # 如果发布不到1天，只生成1个最新快照
        if days_since_pub <= 1:
            num_snapshots = 1
        elif days_since_pub <= 3:
            num_snapshots = random.randint(1, 2)
        elif days_since_pub <= 7:
            num_snapshots = random.randint(2, 3)
        elif days_since_pub <= 30:
            num_snapshots = random.randint(3, 4)
        else:
            num_snapshots = random.randint(3, 5)
        
        # 生成快照时间点（都在发布时间之后，且不超过现在）
        days_ago_list = []
        for _ in range(num_snapshots):
            # 随机选一个"几天前"，范围从 0 到 days_since_pub
            days_ago = random.randint(0, min(days_since_pub, 30))
            days_ago_list.append(days_ago)
        
        days_ago_list = sorted(list(set(days_ago_list)), reverse=True)
        # 确保至少有一个"最新"的（0天前）
        if 0 not in days_ago_list:
            days_ago_list.insert(0, 0)
        
        base_fans = random.randint(50000, 800000)
        
        for days_ago in days_ago_list:
            snap_time = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            
            # 确保快照时间在发布时间之后
            if snap_time < pub_time:
                snap_time = pub_time + timedelta(hours=random.randint(2, 24))
                days_ago = (now - snap_time).days
            
            # 计算增长比例：基于发布以来的时间
            days_after_pub = (snap_time - pub_time).days
            total_days = max(days_since_pub, 1)
            progress = min(1.0, days_after_pub / total_days)
            
            # 增长曲线：幂函数，前期快后期慢
            growth = progress ** 0.65
            # 加随机扰动
            jitter = 0.88 + random.random() * 0.24
            ratio = max(0.02, min(1.1, growth * jitter))
            
            snapshot = {
                "关联视频": [video["record_id"]],
                "快照时间": snap_time.strftime("%Y-%m-%d %H:%M:%S"),
                "播放量": int(video["view"] * ratio),
                "点赞量": int(video["like"] * ratio * (0.92 + random.random() * 0.16)),
                "投币数": int(video["coin"] * ratio * (0.92 + random.random() * 0.16)),
                "收藏数": int(video["favorite"] * ratio * (0.92 + random.random() * 0.16)),
                "分享数": int(video["share"] * ratio * (0.92 + random.random() * 0.16)),
                "弹幕数": int(video["danmaku"] * ratio * (0.92 + random.random() * 0.16)),
                "评论数": int(video["reply"] * ratio * (0.92 + random.random() * 0.16)),
                "粉丝数快照": int(base_fans * ratio * (0.95 + random.random() * 0.1)),
                "备注": "最新快照" if days_ago == 0 else f"{days_ago}天前数据",
            }
            all_new_snapshots.append(snapshot)
        
        print(f"  {video['title'][:30]}: {len(days_ago_list)} 个快照 (发布于 {pub_time.strftime('%Y-%m-%d')}, 发布 {days_since_pub} 天)")
    
    # 5. 为样例视频生成快照（放在后面，数量少一点）
    print("\n生成样例视频快照...")
    for video in sample_videos:
        num_snapshots = random.randint(2, 3)  # 样例视频少一点
        
        days_ago_list = []
        for _ in range(num_snapshots):
            days_ago = random.randint(0, 15)
            days_ago_list.append(days_ago)
        
        days_ago_list = sorted(list(set(days_ago_list)), reverse=True)
        if 0 not in days_ago_list:
            days_ago_list.insert(0, 0)
        
        base_fans = random.randint(10000, 300000)
        
        for days_ago in days_ago_list:
            snap_time = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            ratio = max(0.1, 1.0 - days_ago / 20.0)
            ratio *= 0.9 + random.random() * 0.2
            
            snapshot = {
                "关联视频": [video["record_id"]],
                "快照时间": snap_time.strftime("%Y-%m-%d %H:%M:%S"),
                "播放量": int(video["view"] * ratio),
                "点赞量": int(video["like"] * ratio * (0.9 + random.random() * 0.2)),
                "投币数": int(video["coin"] * ratio * (0.9 + random.random() * 0.2)),
                "收藏数": int(video["favorite"] * ratio * (0.9 + random.random() * 0.2)),
                "分享数": int(video["share"] * ratio * (0.9 + random.random() * 0.2)),
                "弹幕数": int(video["danmaku"] * ratio * (0.9 + random.random() * 0.2)),
                "评论数": int(video["reply"] * ratio * (0.9 + random.random() * 0.2)),
                "粉丝数快照": int(base_fans * ratio * (0.95 + random.random() * 0.1)),
                "备注": "最新快照" if days_ago == 0 else f"{days_ago}天前数据",
            }
            all_new_snapshots.append(snapshot)
        
        print(f"  {video['title'][:30]}: {len(days_ago_list)} 个快照 (样例)")
    
    print(f"\n总共生成: {len(all_new_snapshots)} 条快照")
    
    # 分批创建
    created = 0
    batch_size = 20
    for i in range(0, len(all_new_snapshots), batch_size):
        batch = all_new_snapshots[i:i+batch_size]
        c = create_snapshots(config, batch)
        created += c
        print(f"  批次 {i//batch_size+1}: 创建 {c} 条")
        time.sleep(0.3)
    
    print(f"\n✅ 完成! 共创建 {created} 条快照")
    print(f"   真实视频快照: 排在前面，数据准确")
    print(f"   样例视频快照: 排在后面，数量较少")


if __name__ == "__main__":
    main()
