import json, sys
d = json.load(sys.stdin)
for f in d['data']['fields']:
    print(f"{f['name']}: {f['id']} ({f['type']})")
