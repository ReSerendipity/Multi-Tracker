import os, json, sqlite3, shutil, tempfile, base64
import win32crypt
from Crypto.Cipher import AES

EDGE_USER_DATA = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
COOKIES_PATH = os.path.join(EDGE_USER_DATA, 'Default', 'Network', 'Cookies')
LOCAL_STATE_PATH = os.path.join(EDGE_USER_DATA, 'Local State')

# 1. 获取加密密钥
with open(LOCAL_STATE_PATH, 'r', encoding='utf-8') as f:
    local_state = json.load(f)

encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
encrypted_key = encrypted_key[5:]  # 去掉 "DPAPI" 前缀
key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
print(f"Key length: {len(key)} bytes")

# 2. 读取 cookie
tmp = tempfile.mkdtemp()
tmp_c = os.path.join(tmp, 'Cookies')
shutil.copy2(COOKIES_PATH, tmp_c)

conn = sqlite3.connect(tmp_c)
c = conn.cursor()
c.execute("SELECT name, encrypted_value, host_key FROM cookies WHERE host_key LIKE '%bilibili.com' AND name IN ('SESSDATA', 'DedeUserID', 'bili_jct')")
rows = c.fetchall()
conn.close()
shutil.rmtree(tmp)

# 3. 用 AES-GCM 解密 v20 格式
print("\nTesting v20 AES-GCM decryption:")
for name, enc_val, host_key in rows:
    prefix = enc_val[:3]
    print(f"\n  {name}: prefix={prefix}, len={len(enc_val)}")
    
    if prefix == b'v20':
        # v20 格式: 3 bytes "v20" + 12 bytes nonce + ciphertext + 16 bytes tag
        nonce = enc_val[3:15]
        ciphertext_and_tag = enc_val[15:]
        
        # 尝试不同方式
        # 方式1: 最后16字节是 tag
        ciphertext = ciphertext_and_tag[:-16]
        tag = ciphertext_and_tag[-16:]
        
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
            print(f"    AES-GCM (tag at end): {decrypted[:60]}")
        except Exception as e:
            print(f"    AES-GCM (tag at end) failed: {e}")
        
        # 方式2: 不同的 nonce 长度
        for nonce_len in [12, 16, 8]:
            nonce = enc_val[3:3+nonce_len]
            rest = enc_val[3+nonce_len:]
            ciphertext = rest[:-16]
            tag = rest[-16:]
            if len(ciphertext) > 0:
                try:
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    decrypted = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
                    print(f"    AES-GCM (nonce={nonce_len}): {decrypted[:60]}")
                except Exception as e:
                    pass  # 静默失败
