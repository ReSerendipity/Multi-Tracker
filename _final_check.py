"""最终检查各表数据质量"""
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records


def main():
    config = load_config()
    
    # 博主表
    print("=" * 60)
    print("【博主表】")
    print("=" * 60)
    creators_table = config["tables"]["creators"]["table_id"]
    c_rows = list_records(config, creators_table, ["博主名称", "平台", "B站MID", "抖音SecUID", "小红书用户ID", "快手用户ID", "是否持续跟踪"])
    
    bili = sum(1 for r in c_rows if r.get("B站MID"))
    dy = sum(1 for r in c_rows if r.get("抖音SecUID"))
    xhs = sum(1 for r in c_rows if r.get("小红书用户ID"))
    ks = sum(1 for r in c_rows if r.get("快手用户ID"))
    
    print(f"总数: {len(c_rows)}")
    print(f"  B站博主: {bili}")
    print(f"  抖音博主: {dy}")
    print(f"  小红书博主: {xhs}")
    print(f"  快手博主: {ks}")
    
    # 视频表
    print("\n" + "=" * 60)
    print("【视频表】")
    print("=" * 60)
    videos_table = config["tables"]["videos"]["table_id"]
    v_rows = list_records(config, videos_table, ["视频标题", "平台", "封面"])
    
    by_platform = defaultdict(list)
    for r in v_rows:
        p = str(r.get("平台", "未知"))
        by_platform[p].append(r)
    
    print(f"总数: {len(v_rows)}")
    for p, items in sorted(by_platform.items()):
        has_cover = sum(1 for r in items if r.get("封面"))
        print(f"  {p}: {len(items)} 条 (有封面: {has_cover})")
    
    # 快照表
    print("\n" + "=" * 60)
    print("【快照表】")
    print("=" * 60)
    snapshot_table = config["tables"]["video_metric_snapshots"]["table_id"]
    s_rows = list_records(config, snapshot_table, ["关联视频", "快照时间", "备注", "播放量"])
    
    print(f"总数: {len(s_rows)}")
    
    # 按视频分组，看看每个视频有几个快照
    by_video = defaultdict(list)
    for s in s_rows:
        link = s.get("关联视频")
        vid = ""
        if link and isinstance(link, list) and len(link) > 0:
            item = link[0]
            if isinstance(item, dict):
                vid = item.get("record_id") or ""
            else:
                vid = str(item)
        if vid:
            by_video[vid].append(s)
    
    print(f"涉及视频: {len(by_video)} 个")
    
    # 统计每个视频的快照数量分布
    snap_count_dist = defaultdict(int)
    for vid, snaps in by_video.items():
        snap_count_dist[len(snaps)] += 1
    
    print("快照数量分布:")
    for n in sorted(snap_count_dist.keys()):
        print(f"  {n} 个快照: {snap_count_dist[n]} 个视频")
    
    # 评论表
    print("\n" + "=" * 60)
    print("【评论表】")
    print("=" * 60)
    comments_table = config["tables"]["video_comments"]["table_id"]
    cm_rows = list_records(config, comments_table, ["用户昵称", "评论层级", "点赞数", "关联视频"])
    
    print(f"总评论数: {len(cm_rows)}")
    
    level1 = sum(1 for r in cm_rows if r.get("评论层级") == 1 or r.get("评论层级") == "1")
    level2 = len(cm_rows) - level1
    print(f"  一级评论: {level1}")
    print(f"  二级回复: {level2}")
    
    by_video = defaultdict(int)
    for r in cm_rows:
        link = r.get("关联视频")
        vid = ""
        if link and isinstance(link, list) and len(link) > 0:
            item = link[0]
            if isinstance(item, dict):
                vid = item.get("record_id") or ""
            else:
                vid = str(item)
        if vid:
            by_video[vid] += 1
    
    print(f"  覆盖视频: {len(by_video)} 个")


if __name__ == "__main__":
    main()
