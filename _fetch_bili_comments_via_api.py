"""
直接用B站API抓取评论并写入飞书评论表
B站评论API是公开的，不需要CDP和登录
"""
import sys, json, time, random, requests
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark


BILI_COMMENT_API = "https://api.bilibili.com/x/v2/reply"

def fetch_bili_comments(bvid, max_root=20, max_replies=3):
    """从B站API抓取评论"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}",
    }
    
    comments = []
    page = 1
    total_root = 0
    
    while total_root < max_root:
        params = {
            "type": 1,  # 1 = 视频评论
            "oid": bvid_to_aid(bvid),
            "sort": 2,  # 2 = 按热度排序
            "pn": page,
            "ps": 20,
        }
        
        try:
            resp = requests.get(BILI_COMMENT_API, params=params, headers=headers, timeout=10)
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
                
                # 一级评论
                comments.append({
                    "评论ID": str(rpid),
                    "评论内容": content,
                    "用户昵称": uname,
                    "用户ID": str(mid),
                    "用户性别": sex,
                    "头像链接": avatar,
                    "用户签名": sign,
                    "点赞数": like,
                    "回复数": rcount,
                    "评论时间": ctime_str,
                    "评论层级": 1,
                    "父评论ID": "",
                    "根评论ID": str(rpid),
                    "BVID": bvid,
                })
                
                # 抓取部分回复
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
                            "评论内容": sub_content,
                            "用户昵称": sub_uname,
                            "用户ID": str(sub_mid),
                            "用户性别": sub_sex,
                            "头像链接": sub_avatar,
                            "用户签名": sub_sign,
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
            time.sleep(0.5)
            
        except Exception as e:
            print(f"    抓取失败: {e}")
            break
    
    return comments


def bvid_to_aid(bvid):
    """BVID转AID（用API查）"""
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
    # 备用：返回0，让API自己处理（部分接口支持bvid）
    return 0


def write_comments_to_feishu(config, comments_table_id, video_record_id, comments, max_rows=15):
    """把评论写入飞书"""
    if not comments:
        return 0
    
    # 只取前max_rows条写入表格
    comments_to_write = comments[:max_rows]
    
    fields = [
        "评论ID", "评论内容", "用户昵称", "用户ID", "用户性别",
        "头像链接", "用户签名", "点赞数", "回复数", "评论时间",
        "评论层级", "父评论ID", "根评论ID", "BVID", "关联视频",
        "采集时间",
    ]
    
    collect_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_data = []
    for c in comments_to_write:
        row = [
            c["评论ID"], c["评论内容"], c["用户昵称"], c["用户ID"], c["用户性别"],
            c["头像链接"], c["用户签名"], c["点赞数"], c["回复数"], c["评论时间"],
            c["评论层级"], c["父评论ID"], c["根评论ID"], c["BVID"],
            [video_record_id],  # 关联视频
            collect_time,
        ]
        rows_data.append(row)
    
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    pf = tmp / f"comments_{video_record_id}.json"
    pf.write_text(json.dumps({"fields": fields, "rows": rows_data}), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+record-batch-create",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", comments_table_id,
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
    
    # 获取B站视频
    v_fields = ["视频标题", "BVID", "平台", "评论抓取状态"]
    video_rows = list_records(config, videos_table, v_fields)
    bili_videos = [r for r in video_rows if r.get("平台") == "B站" and r.get("BVID")]
    
    # 过滤掉已经抓取过评论的
    pending = [r for r in bili_videos if r.get("评论抓取状态") != "已抓取"]
    print(f"B站视频总数: {len(bili_videos)}")
    print(f"待抓取评论: {len(pending)}")
    
    # 限制处理数量
    max_videos = min(10, len(pending))
    print(f"本次处理前 {max_videos} 个视频")
    
    total_fetched = 0
    total_written = 0
    
    for i, video in enumerate(pending[:max_videos]):
        bvid = video["BVID"]
        title = str(video.get("视频标题", ""))[:40]
        vid = video["_record_id"]
        
        print(f"\n[{i+1}/{max_videos}] {title}")
        print(f"  BVID: {bvid}")
        
        # 抓取评论
        comments = fetch_bili_comments(bvid, max_root=20, max_replies=2)
        total_fetched += len(comments)
        print(f"  抓取到 {len(comments)} 条评论")
        
        if comments:
            # 写入飞书
            written = write_comments_to_feishu(config, comments_table, vid, comments, max_rows=15)
            total_written += written
            print(f"  写入飞书: {written} 条")
            
            # 更新视频的评论状态
            try:
                tmp = ROOT / ".tmp-lark"
                pf = tmp / f"v_upd_{vid}.json"
                pf.write_text(json.dumps({
                    "评论抓取状态": "已抓取",
                    "已抓评论数": len(comments),
                    "最近采集时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }), encoding="utf-8")
                
                run_lark(config, [
                    "+record-upsert",
                    "--as", "user",
                    "--base-token", config["base_token"],
                    "--table-id", videos_table,
                    "--record-id", vid,
                    "--json", f"@{pf.relative_to(ROOT)}",
                ], timeout=20)
                pf.unlink(missing_ok=True)
            except Exception as e:
                print(f"  更新视频状态失败: {e}")
        
        time.sleep(1)
    
    print(f"\n=== 结果 ===")
    print(f"处理视频: {min(max_videos, len(pending))} 个")
    print(f"抓取评论: {total_fetched} 条")
    print(f"写入飞书: {total_written} 条")


if __name__ == "__main__":
    main()
