import os, json, sqlite3, shutil, tempfile, base64
import win32crypt
from Crypto.Cipher import AES

EDGE_USER_DATA = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
COOKIES_PATH = os.path.join(EDGE_USER_DATA, 'Default', 'Network', 'Cookies')
LOCAL_STATE_PATH = os.path.join(EDGE_USER_DATA, 'Local State')

# 1. 获取加密密钥
print("[1] 读取加密密钥...")
with open(LOCAL_STATE_PATH, 'r', encoding='utf-8') as f:
    local_state = json.load(f)

encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
print(f"  encrypted_key prefix: {encrypted_key[:5]}")
print(f"  encrypted_key length: {len(encrypted_key)}")

# 去掉 "DPAPI" 前缀
encrypted_key = encrypted_key[5:]
key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
print(f"  decrypted key length: {len(key)} bytes")

# 2. 读取 cookie
print("\n[2] 读取 B 站 Cookie...")
tmp = tempfile.mkdtemp()
tmp_c = os.path.join(tmp, 'Cookies')
shutil.copy2(COOKIES_PATH, tmp_c)

conn = sqlite3.connect(tmp_c)
c = conn.cursor()
c.execute("SELECT name, encrypted_value, host_key FROM cookies WHERE host_key LIKE '%bilibili.com' AND name IN ('SESSDATA', 'DedeUserID', 'bili_jct')")
rows = c.fetchall()
conn.close()
shutil.rmtree(tmp)

print(f"  Found {len(rows)} important cookies")

# 3. 解密测试
print("\n[3] 解密测试...")
for name, enc_val, host_key in rows:
    print(f"\n  {name} ({host_key}):")
    print(f"    encrypted length: {len(enc_val)}")
    print(f"    first 5 bytes: {enc_val[:5]}")
    
    if enc_val[:3] in (b'v10', b'v11'):
        print(f"    format: v10/v11 (AES-GCM)")
        try:
            nonce = enc_val[3:15]
            ciphertext = enc_val[15:-16]
            tag = enc_val[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
            print(f"    decrypted: {decrypted[:50]}...")
        except Exception as e:
            print(f"    decryption failed: {e}")
    else:
        print(f"    format: DPAPI (old)")
        try:
            decrypted = win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1].decode('utf-8', errors='replace')
            print(f"    decrypted: {decrypted[:50]}...")
        except Exception as e:
            print(f"    decryption failed: {e}")
