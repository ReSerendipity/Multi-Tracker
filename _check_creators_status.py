"""查看飞书博主表当前状态"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from download_bili_following_latest import load_config, list_records, field_names
from collections import Counter

config = load_config()
table_id = config['tables']['creators']['table_id']

# 获取所有字段
all_fields = field_names(config, table_id)
print('博主表字段:', all_fields)

# 获取所有记录
desired = ['博主名称', '平台', '抖音SecUID', '抖音主页链接', '抖音持续跟踪', 
           '快手用户ID', '快手主页链接', '快手持续跟踪', 
           '小红书用户ID', '小红书主页链接', '小红书持续跟踪']
fields = [f for f in desired if f in all_fields]
rows = list_records(config, table_id, fields)

print(f'\n博主总数: {len(rows)}')

# 按平台统计
platforms = Counter()
for row in rows:
    p = row.get('平台', [])
    if isinstance(p, list):
        for plat in p:
            platforms[str(plat)] += 1
    elif p:
        platforms[str(p)] += 1

print('\n各平台博主数:')
for p, c in platforms.items():
    print(f'  {p}: {c}')

print('\n抖音博主详情:')
for row in rows:
    plats = row.get('平台', [])
    plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
    if '抖音' in plat_list:
        sec_uid = row.get('抖音SecUID', '') or '无'
        url = row.get('抖音主页链接', '') or '无'
        print(f"  - {row.get('博主名称', '')}: SecUID={sec_uid}, 链接={url}")

print('\n快手博主详情:')
for row in rows:
    plats = row.get('平台', [])
    plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
    if '快手' in plat_list:
        user_id = row.get('快手用户ID', '') or '无'
        url = row.get('快手主页链接', '') or '无'
        print(f"  - {row.get('博主名称', '')}: 用户ID={user_id}, 链接={url}")

print('\n小红书博主详情:')
for row in rows:
    plats = row.get('平台', [])
    plat_list = plats if isinstance(plats, list) else [str(plats)] if plats else []
    if '小红书' in plat_list:
        user_id = row.get('小红书用户ID', '') or '无'
        url = row.get('小红书主页链接', '') or '无'
        print(f"  - {row.get('博主名称', '')}: 用户ID={user_id}, 链接={url}")
