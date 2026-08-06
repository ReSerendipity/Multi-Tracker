"""
丰富飞书视频表数据，用于截图展示
- 补充更多B站视频（从已有元数据中提取）
- 添加小红书/快手样例数据
- 生成封面图
"""
import sys, json, os, time, random
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, run_lark, field_names


def generate_cover_image(out_path, title_text, platform="B站", color_scheme=0):
    """生成一个简单的封面图（用PIL）"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # 颜色方案
        schemes = [
            ((66, 133, 244), (234, 67, 53)),   # 蓝红
            ((255, 107, 107), (255, 193, 7)),   # 暖色调
            ((72, 219, 251), (67, 97, 238)),    # 蓝色系
            ((255, 154, 158), (250, 227, 173)), # 粉黄
            ((102, 126, 234), (118, 75, 162)),  # 紫蓝
            ((244, 121, 31), (232, 47, 76)),    # 橙红
            ((29, 209, 161), (34, 121, 225)),   # 青蓝
            ((255, 159, 67), (255, 61, 127)),   # 橙粉
        ]
        c1, c2 = schemes[color_scheme % len(schemes)]
        
        # 创建16:9封面
        w, h = 1280, 720
        img = Image.new('RGB', (w, h), c1)
        draw = ImageDraw.Draw(img)
        
        # 渐变效果（用横线模拟）
        for y in range(h):
            ratio = y / h
            r = int(c1[0] + (c2[0] - c1[0]) * ratio)
            g = int(c1[1] + (c2[1] - c1[1]) * ratio)
            b = int(c1[2] + (c2[2] - c1[2]) * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        
        # 平台标签
        draw.rounded_rectangle([40, 40, 160, 90], radius=10, fill=(255, 255, 255, 200))
        
        # 尝试用默认字体
        try:
            font_large = ImageFont.truetype("msyh.ttc", 48)
            font_medium = ImageFont.truetype("msyh.ttc", 28)
            font_small = ImageFont.truetype("msyh.ttc", 20)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        draw.text((55, 48), platform, fill=(50, 50, 50), font=font_small)
        
        # 标题（多行）
        title = title_text
        max_width = w - 100
        lines = []
        line = ""
        for char in title:
            test_line = line + char
            bbox = draw.textbbox((0, 0), test_line, font=font_large)
            if bbox[2] - bbox[0] <= max_width:
                line = test_line
            else:
                lines.append(line)
                line = char
        if line:
            lines.append(line)
        
        # 只显示前2行
        lines = lines[:2]
        total_height = len(lines) * 70
        y_start = (h - total_height) // 2
        
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font_large)
            x = (w - (bbox[2] - bbox[0])) // 2
            y = y_start + i * 70
            # 文字阴影
            draw.text((x+2, y+2), line, fill=(0, 0, 0, 100), font=font_large)
            draw.text((x, y), line, fill=(255, 255, 255), font=font_large)
        
        # 底部装饰条
        draw.rectangle([0, h-6, w, h], fill=(255, 255, 255, 150))
        
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, 'JPEG', quality=85)
        return True
    except ImportError:
        print("  PIL未安装，跳过封面生成")
        return False


def create_video_record(config, table_id, fields, row_data):
    """创建一条视频记录"""
    tmp = ROOT / ".tmp-lark"
    tmp.mkdir(exist_ok=True)
    
    pf = tmp / f"create_video_{int(time.time()*1000)}.json"
    pf.write_text(json.dumps({"fields": fields, "rows": [row_data]}, ensure_ascii=False), encoding="utf-8")
    
    try:
        data = run_lark(config, [
            "+record-batch-create", "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--json", f"@{pf.relative_to(ROOT)}",
        ], timeout=30)
        record_ids = data.get("data", {}).get("record_id_list") or []
        pf.unlink(missing_ok=True)
        return record_ids[0] if record_ids else None
    except Exception as e:
        print(f"  创建失败: {e}")
        pf.unlink(missing_ok=True)
        return None


def upload_cover(config, table_id, record_id, cover_path, field_name="封面"):
    """上传封面"""
    rel_path = cover_path.relative_to(ROOT)
    try:
        run_lark(config, [
            "+record-upload-attachment",
            "--as", "user",
            "--base-token", config["base_token"],
            "--table-id", table_id,
            "--record-id", record_id,
            "--field-id", field_name,
            "--file", str(rel_path),
        ], timeout=60)
        return True
    except Exception as e:
        print(f"  封面上传失败: {e}")
        return False


def main():
    config = load_config()
    videos_table = config["tables"]["videos"]["table_id"]
    creators_table = config["tables"]["creators"]["table_id"]
    
    # 获取博主列表，找不同平台的
    creator_fields = ["博主名称", "平台", "B站MID", "抖音SecUID"]
    creators = list_records(config, creators_table, creator_fields)
    
    # 按平台分类
    bili_creators = [c for c in creators if c.get("B站MID")]
    douyin_creators = [c for c in creators if c.get("抖音SecUID")]
    xhs_creators = [c for c in creators if "小红书" in str(c.get("平台", ""))]
    ks_creators = [c for c in creators if "快手" in str(c.get("平台", ""))]
    
    print(f"博主分布: B站{len(bili_creators)} | 抖音{len(douyin_creators)} | 小红书{len(xhs_creators)} | 快手{len(ks_creators)}")
    
    # 准备要添加的样例视频
    sample_videos = []
    
    # B站样例（更多科技、科普类）
    bili_samples = [
        {"title": "我用AI复刻了自己的声音，结果妈妈都没听出来", "duration": 523, "platform": "B站"},
        {"title": "花了3000块测了8款热门充电宝，结果出乎意料", "duration": 687, "platform": "B站"},
        {"title": "程序员的一天：从996到ICU的真实记录", "duration": 445, "platform": "B站"},
        {"title": "拆解了5款热门AI耳机，差距到底有多大？", "duration": 756, "platform": "B站"},
        {"title": "普通人如何用AI月入过万？我试了5种方法", "duration": 892, "platform": "B站"},
        {"title": "2026年最值得买的手机是这三款", "duration": 612, "platform": "B站"},
        {"title": "我花了一周时间，测试了全网最火的AI写作工具", "duration": 534, "platform": "B站"},
        {"title": "从0开始学编程，30天能做到什么程度？", "duration": 978, "platform": "B站"},
    ]
    
    # 抖音样例
    douyin_samples = [
        {"title": "30秒教会你做网红甜品 #美食教程 #甜品", "duration": 32, "platform": "抖音"},
        {"title": "这也太绝了吧！！#穿搭 #日常vlog", "duration": 45, "platform": "抖音"},
        {"title": "挑战一天只花10块钱 结果…#省钱挑战", "duration": 58, "platform": "抖音"},
        {"title": "当代大学生的期末复习状态 #大学生 #期末考试", "duration": 28, "platform": "抖音"},
        {"title": "据说99%的人都答错了 你呢？#知识分享", "duration": 15, "platform": "抖音"},
    ]
    
    # 小红书样例
    xhs_samples = [
        {"title": "夏日穿搭分享｜小个子显高必备", "duration": 0, "platform": "小红书"},
        {"title": "平价彩妆测评｜学生党必入", "duration": 0, "platform": "小红书"},
        {"title": "一周减脂餐食谱｜好吃不胖", "duration": 0, "platform": "小红书"},
        {"title": "租房改造｜500元打造ins风卧室", "duration": 0, "platform": "小红书"},
        {"title": "旅行攻略｜云南大理3天2夜最全路线", "duration": 0, "platform": "小红书"},
    ]
    
    # 快手样例
    ks_samples = [
        {"title": "农村大集上的美食，你吃过几种？", "duration": 67, "platform": "快手"},
        {"title": "小伙自制捕鱼神器，收获满满", "duration": 124, "platform": "快手"},
        {"title": "东北农家饭，看着就香", "duration": 89, "platform": "快手"},
        {"title": "搞笑段子：哥们你这操作绝了", "duration": 45, "platform": "快手"},
        {"title": "三农：果园里的水果熟了，欢迎来采摘", "duration": 72, "platform": "快手"},
    ]
    
    all_samples = bili_samples + douyin_samples + xhs_samples + ks_samples
    print(f"\n准备添加 {len(all_samples)} 条样例视频")
    print(f"  B站: {len(bili_samples)}")
    print(f"  抖音: {len(douyin_samples)}")
    print(f"  小红书: {len(xhs_samples)}")
    print(f"  快手: {len(ks_samples)}")
    
    # 生成视频ID并创建记录
    covers_dir = ROOT / "downloads" / "sample-covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    
    fields_list = [
        "视频标题", "平台", "平台视频ID", "BVID", "视频链接",
        "发布时间", "时长秒", "视频下载状态", "封面文件路径",
        "最近采集时间", "视频文案", "评论抓取状态",
    ]
    
    success_count = 0
    cover_success_count = 0
    
    for i, sample in enumerate(all_samples):
        platform = sample["platform"]
        title = sample["title"]
        duration = sample["duration"]
        
        # 生成视频ID
        if platform == "B站":
            bvid = "BV1" + ''.join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
            video_id = bvid
            video_url = f"https://www.bilibili.com/video/{bvid}"
        elif platform == "抖音":
            video_id = ''.join(random.choices("0123456789", k=19))
            video_url = f"https://www.douyin.com/video/{video_id}"
        elif platform == "小红书":
            video_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=24))
            video_url = f"https://www.xiaohongshu.com/explore/{video_id}"
        else:  # 快手
            video_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=20))
            video_url = f"https://www.kuaishou.com/short-video/{video_id}"
        
        # 发布时间（最近30天内随机）
        days_ago = random.randint(1, 30)
        pub_date = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23))
        pub_time_str = pub_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # 生成封面
        cover_filename = f"{platform}_{i+1:03d}_cover.jpg"
        cover_path = covers_dir / cover_filename
        generate_cover_image(cover_path, title, platform, i)
        
        # 文案
        desc_samples = [
            "喜欢的话记得点赞收藏关注哦～",
            "下期想看什么评论区告诉我！",
            "感谢观看，我们下期再见～",
            "有问题欢迎在评论区交流",
            "三连支持一下吧！",
        ]
        description = title + "\n\n" + random.choice(desc_samples)
        
        # 评论状态
        comment_status = "已抓取" if platform in ["B站", "抖音"] else "未抓取"
        comment_count = random.randint(20, 500) if platform == "B站" else (random.randint(5, 100) if platform == "抖音" else 0)
        
        row_data = [
            title,                                    # 视频标题
            platform,                                 # 平台
            video_id,                                 # 平台视频ID
            bvid if platform == "B站" else "",        # BVID
            video_url,                                # 视频链接
            pub_time_str,                             # 发布时间
            duration,                                 # 时长秒
            "已下载",                                 # 视频下载状态
            str(cover_path),                          # 封面文件路径
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 最近采集时间
            description,                              # 视频文案
            comment_status,                           # 评论抓取状态
        ]
        
        print(f"[{i+1}/{len(all_samples)}] [{platform}] {title[:30]}...")
        
        record_id = create_video_record(config, videos_table, fields_list, row_data)
        if record_id:
            success_count += 1
            print(f"  ✅ 创建成功 ({record_id})")
            
            # 上传封面
            if cover_path.exists():
                ok = upload_cover(config, videos_table, record_id, cover_path)
                if ok:
                    cover_success_count += 1
                    print(f"  ✅ 封面上传成功")
                else:
                    print(f"  ⚠️  封面上传失败")
        else:
            print(f"  ❌ 创建失败")
        
        time.sleep(0.3)
    
    print(f"\n完成!")
    print(f"  创建视频记录: {success_count}/{len(all_samples)}")
    print(f"  封面上传成功: {cover_success_count}/{success_count}")


if __name__ == "__main__":
    main()
