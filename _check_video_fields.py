"""查看视频表字段"""
import sys
sys.path.insert(0, '.')
from download_bili_following_latest import load_config, field_names

config = load_config()
table_id = config['tables']['videos']['table_id']
fields = field_names(config, table_id)
print('视频表字段:')
for name, info in fields.items():
    print(f'  {name}: {info["type"]}')
