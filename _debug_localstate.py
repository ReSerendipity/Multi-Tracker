import os, json

LOCAL_STATE_PATH = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data', 'Local State')

with open(LOCAL_STATE_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 查看 os_crypt 部分
print("os_crypt keys:")
os_crypt = data.get('os_crypt', {})
for k in os_crypt.keys():
    v = os_crypt[k]
    if isinstance(v, str) and len(v) > 50:
        print(f"  {k}: (length {len(v)} str)")
    else:
        print(f"  {k}: {v}")

# 查看所有顶层 key
print("\nTop-level keys:")
for k in sorted(data.keys()):
    v = data[k]
    if isinstance(v, dict):
        print(f"  {k}: (dict with {len(v)} keys)")
    elif isinstance(v, str) and len(v) > 50:
        print(f"  {k}: (length {len(v)} str)")
    else:
        print(f"  {k}: {v}")

# 检查是否有 encryption_key 相关
def find_keys(obj, path=''):
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if 'key' in k.lower() or 'encrypt' in k.lower() or 'crypt' in k.lower():
                results.append(f"{path}.{k}" if path else k)
            if isinstance(v, (dict, list)):
                results.extend(find_keys(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                results.extend(find_keys(v, f"{path}[{i}]"))
    return results

print("\nAll encryption-related keys:")
for k in find_keys(data):
    print(f"  {k}")
