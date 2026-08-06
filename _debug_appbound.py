import os, json, sqlite3, shutil, tempfile, base64
import win32crypt
from Crypto.Cipher import AES

EDGE_USER_DATA = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
COOKIES_PATH = os.path.join(EDGE_USER_DATA, 'Default', 'Network', 'Cookies')
LOCAL_STATE_PATH = os.path.join(EDGE_USER_DATA, 'Local State')

with open(LOCAL_STATE_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

os_crypt = data['os_crypt']

# 解密各种密钥
for key_name in ['encrypted_key', 'app_bound_encrypted_key', 'aster_app_bound_encrypted_key']:
    enc_b64 = os_crypt.get(key_name, '')
    if not enc_b64:
        continue
    enc = base64.b64decode(enc_b64)
    print(f"\n{key_name}:")
    print(f"  raw length: {len(enc)} bytes")
    print(f"  prefix: {enc[:10]}")
    
    # 尝试不同的前缀处理
    for skip in [0, 5, 8, 12, 16]:
        try:
            dec = win32crypt.CryptUnprotectData(enc[skip:], None, None, None, 0)[1]
            print(f"  DPAPI (skip={skip}): key length = {len(dec)} bytes")
        except Exception as e:
            pass

# 读取 SESSDATA cookie
tmp = tempfile.mkdtemp()
tmp_c = os.path.join(tmp, 'Cookies')
shutil.copy2(COOKIES_PATH, tmp_c)
conn = sqlite3.connect(tmp_c)
c = conn.cursor()
c.execute("SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%bilibili.com' AND name = 'SESSDATA'")
row = c.fetchone()
conn.close()
shutil.rmtree(tmp)

if not row:
    print("\nNo SESSDATA found!")
    exit()

name, enc_val = row
print(f"\n\nSESSDATA encrypted: len={len(enc_val)}, prefix={enc_val[:5]}")

# 尝试用 app_bound key 解密
enc_key_b64 = os_crypt['app_bound_encrypted_key']
enc_key = base64.b64decode(enc_key_b64)

# 尝试不同方式获取 key
for skip_desc, skip_bytes in [('no prefix', 0), ('DPAPI', 5), ('v20', 3)]:
    try:
        key = win32crypt.CryptUnprotectData(enc_key[skip_bytes:], None, None, None, 0)[1]
        print(f"\nTrying key from app_bound (skip={skip_desc}), len={len(key)}:")
        
        # 尝试 AES-GCM v20 格式
        if enc_val[:3] == b'v20':
            nonce = enc_val[3:15]
            ciphertext = enc_val[15:-16]
            tag = enc_val[-16:]
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
                print(f"  SUCCESS! SESSDATA = {decrypted[:60]}...")
            except Exception as e:
                print(f"  GCM failed: {e}")
    except Exception as e:
        print(f"\nDPAPI decryption failed (skip={skip_desc}): {e}")
