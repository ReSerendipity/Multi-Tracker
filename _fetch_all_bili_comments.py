"""
用B站API抓取评论并写入飞书 - 强制重抓所有B站视频
"""
import sys, json, time, random, requests
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


def bvid_to_aid(bvid):
    """BVID转AID"""
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return data["data"]["aid"]
    except:
        pass
    return 0


def fetch_bili_comments(bvid, max_root=15, max_replies=3):
    """从B站API抓取评论"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}",
    }
    
    aid = bvid_to_aid(bvid)
    if not aid:
        print(f"    无法获取AID")
        return []
    
    comments = []
    page = 1
    total_root = 0
    
    while total_root < max_root:
        params = {
            "type": 1,
            "oid": aid,
            "sort": 2,
            "pn": page,
            "ps": 20,
        }
        
        try:
            resp = requests.get("https://api.bilibili.com/x/v2/reply", params=params, headers=headers, timeout=10)
            data = resp.json()
            
            if data.get("code") != 0:
                print(f"    API错误: {data.get('message')}")
                break
            
            replies = data.get("data", {}).get("replies") or []
            if not replies:
                break
            
            for reply in replies:
                if total_root >= max_root:
                    break
                
                rpid = reply.get("rpid", "")
                content = reply.get("content", {}).get("message", "")
                member = reply.get("member", {})
                uname = member.get("uname", "")
                mid = member.get("mid", "")
                avatar = member.get("avatar", "")
                sex = member.get("sex", "保密")
                sign = member.get("sign", "")
                like = reply.get("like", 0)
                rcount = reply.get("rcount", 0)
                ctime = reply.get("ctime", 0)
                ctime_str = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else ""
                
                comments.append({
                    "评论ID": str(rpid),
                    "评论内容": content[:500],
                    "用户昵称": uname,
                    "用户ID": str(mid),
                    "用户性别": sex,
                    "头像链接": avatar,
                    "用户签名": sign[:100],
                    "点赞数": like,
                    "回复数": rcount,
                    "评论时间": ctime_str,
                    "评论层级": 1,
                    "父评论ID": "",
                    "根评论ID": str(rpid),
                    "BVID": bvid,
                })
                
                # 回复
                if rcount > 0 and max_replies > 0:
                    sub_replies = reply.get("replies") or []
                    for sub in sub_replies[:max_replies]:
                        sub_rpid = sub.get("rpid", "")
                        sub_content = sub.get("content", {}).get("message", "")
                        sub_member = sub.get("member", {})
                        sub_uname = sub_member.get("uname", "")
                        sub_mid = sub_member.get("mid", "")
                        sub_avatar = sub_member.get("avatar", "")
                        sub_sex = sub_member.get("sex", "保密")
                        sub_sign = sub_member.get("sign", "")
                        sub_like = sub.get("like", 0)
                        sub_ctime = sub.get("ctime", 0)
                        sub_ctime_str = datetime.fromtimestamp(sub_ctime).strftime("%Y-%m-%d %H:%M:%S") if sub_ctime else ""
                        sub_parent = sub.get("parent", rpid)
                        
                        comments.append({
                            "评论ID": str(sub_rpid),
                            "评论内容": sub_content[:500],
                            "用户昵称": sub_uname,
                            "用户ID": str(sub_mid),
                            "用户性别": sub_sex,
                            "头像链接": sub_avatar,
                            "用户签名": sub_sign[:100],
                            "点赞数": sub_like,
                            "回复数": 0,
                            "评论时间": sub_ctime_str,
                            "评论层级": 2,
                            "父评论ID": str(sub_parent),
                            "根评论ID": str(rpid),
                            "BVID": bvid,
                        })
                
                total_root += 1
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            print(f"    抓取失败: {e}")
            break
    
    return comments


def write_comments(config, table_id, video_record_id, comments, max_rows=12):
    """写入飞书评论表"""
    if not comments:
        return 0
    
    comments_to_write = comments[:max_rows]
    
    fields = [
        "评论ID", "评论内容", "用户昵称", "用户ID", "用户性别",
        "头像链接", "用户签名", "点赞数", "回复数", "评论时间",
        "评论层级", "父评论ID", "根评论ID", "BVID", "关联视频", "采集时间",
    ]
    
    collect_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_data = []
    for c in comments_to_write:
        row = [
            c["评论ID"], c["评论内容"], c["用户昵称"], c["用户ID"], c["用户性别"],
            c["头像链接"], c["用户签名"], c["点赞数"], c["回复数"], c["评论时间"],
            c["评论层级"], c["父评论ID"], c["根评论ID"], c["BVID"],
            [video_record_id],
            collect_time,
        ]
        rows_data.append(row)
    
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"cmt_{video_record_id}.json"
    pf.write_text(json.dumps({"fields": fields, "rows": rows_data}), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+record-batch-create",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        record_ids = data.get("data", {}).get("record_id_list") or []
        pf.unlink(missing_ok=True)
        return len(record_ids)
    except Exception as e:
        print(f"    写入失败: {e}")
        pf.unlink(missing_ok=True)
        return 0


def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    comments_table = config["tables"]["video_comments"]["table_id"]
    
    # 获取所有B站视频
    v_fields = ["视频标题", "BVID", "平台"]
    video_rows = list_records(config, videos_table, v_fields)
    bili_videos = [r for r in video_rows if r.get("平台") == "B站" and r.get("BVID")]
    
    print(f"B站视频: {len(bili_videos)}")
    
    total_fetched = 0
    total_written = 0
    
    for i, video in enumerate(bili_videos):
        bvid = video["BVID"]
        title = str(video.get("视频标题", ""))[:40]
        vid = video["_record_id"]
        
        print(f"\n[{i+1}/{len(bili_videos)}] {title}")
        
        comments = fetch_bili_comments(bvid, max_root=12, max_replies=2)
        total_fetched += len(comments)
        print(f"  抓取: {len(comments)} 条")
        
        if comments:
            written = write_comments(config, comments_table, vid, comments, max_rows=12)
            total_written += written
            print(f"  写入: {written} 条")
        
        time.sleep(0.5)
    
    print(f"\n=== 结果 ===")
    print(f"处理视频: {len(bili_videos)} 个")
    print(f"抓取评论: {total_fetched} 条")
    print(f"写入飞书: {total_written} 条")


if __name__ == "__main__":
    main()
