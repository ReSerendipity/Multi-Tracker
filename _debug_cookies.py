import os, sqlite3, shutil, tempfile

cookie_path = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data', 'Default', 'Network', 'Cookies')
print(f'Cookie file exists: {os.path.exists(cookie_path)}')
print(f'Cookie file size: {os.path.getsize(cookie_path)} bytes')

tmp = tempfile.mkdtemp()
tmp_c = os.path.join(tmp, 'Cookies')
shutil.copy2(cookie_path, tmp_c)

conn = sqlite3.connect(tmp_c)
c = conn.cursor()

# 查看所有 host_key
c.execute('SELECT DISTINCT host_key FROM cookies ORDER BY host_key')
hosts = c.fetchall()
print(f'\nTotal distinct hosts: {len(hosts)}')
print('Hosts containing bili:')
for h in hosts:
    if 'bili' in h[0].lower():
        print(f'  {h[0]}')

# 查看 B 站 cookie 数量
c.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%bilibili%'")
count = c.fetchone()[0]
print(f'\nBilibili cookie count: {count}')

if count > 0:
    c.execute("SELECT name, LENGTH(encrypted_value), host_key FROM cookies WHERE host_key LIKE '%bilibili%' LIMIT 15")
    for row in c.fetchall():
        print(f'  {row[0]} ({row[1]} bytes) - {row[2]}')

conn.close()
shutil.rmtree(tmp)
