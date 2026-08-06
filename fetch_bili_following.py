"""
直接从 Edge 的 Cookie 数据库解密 v20 格式 cookies
Edge 必须已关闭
"""
import json
import os
import sqlite3
import tempfile
import shutil
import base64
import urllib.request
import urllib.error
import sys


def get_bilibili_cookies():
    """解密 Edge 的 v20 Cookie，返回 B 站相关 cookie"""
    # 路径
    local_appdata = os.environ['LOCALAPPDATA']
    user_data = os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data')
    local_state_path = os.path.join(user_data, 'Local State')
    cookie_path = os.path.join(user_data, 'Default', 'Network', 'Cookies')
    
    # 检查文件
    if not os.path.exists(cookie_path):
        cookie_path = os.path.join(user_data, 'Default', 'Cookies')  # 旧位置
    
    print(f'Cookie 文件: {cookie_path}')
    print(f'Local State: {local_state_path}')
    
    if not os.path.exists(cookie_path):
        print('错误: 找不到 Cookie 文件！')
        return None
    
    # 1. 从 Local State 获取加密密钥
    with open(local_state_path, 'r', encoding='utf-8') as f:
        local_state = json.load(f)
    
    encrypted_key_b64 = local_state['os_crypt'].get('encrypted_key')
    if not encrypted_key_b64:
        print('错误: Local State 中没有 encrypted_key！')
        return None
    
    encrypted_key = base64.b64decode(encrypted_key_b64)
    print(f'加密密钥长度: {len(encrypted_key)} bytes')
    print(f'密钥前缀: {encrypted_key[:5]}')
    
    # 去掉 "DPAPI" 前缀 (5 bytes)
    if encrypted_key[:5] == b'DPAPI':
        encrypted_key = encrypted_key[5:]
        print('检测到 DPAPI 前缀，正在解密...')
    else:
        print('警告: 密钥没有 DPAPI 前缀，尝试直接使用')
    
    # 用 DPAPI 解密密钥
    import win32crypt
    try:
        key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        print(f'密钥解密成功！长度: {len(key)} bytes')
    except Exception as e:
        print(f'密钥解密失败: {e}')
        return None
    
    # 2. 复制 Cookie 数据库到临时文件（避免锁定）
    tmp = tempfile.mkdtemp()
    tmp_cookie = os.path.join(tmp, 'Cookies')
    shutil.copy2(cookie_path, tmp_cookie)
    
    # 3. 查询 B 站相关 cookies
    conn = sqlite3.connect(tmp_cookie)
    c = conn.cursor()
    
    # 查看 cookie 表结构
    c.execute("PRAGMA table_info(cookies)")
    columns = [col[1] for col in c.fetchall()]
    print(f'\nCookie 表字段: {columns}')
    
    # 查询 B 站 cookies
    c.execute("""
        SELECT name, encrypted_value, host_key 
        FROM cookies 
        WHERE host_key LIKE '%bilibili%' 
           OR host_key LIKE '%bili%'
        ORDER BY host_key, name
    """)
    rows = c.fetchall()
    print(f'找到 {len(rows)} 个 B 站相关 Cookie')
    
    # 4. 解密每个 cookie
    from Crypto.Cipher import AES
    
    cookies = {}
    for name, enc_val, host_key in rows:
        decrypted = None
        
        # v20 格式: 前3字节是 "v20"
        if enc_val[:3] == b'v20':
            # v20: AES-256-GCM
            # 格式: v20 (3 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
            nonce = enc_val[3:15]
            ciphertext = enc_val[15:-16]
            tag = enc_val[-16:]
            
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
            except Exception as e:
                print(f'  {name} v20 解密失败: {e}')
                continue
        
        # v10/v11 格式
        elif enc_val[:3] in (b'v10', b'v11'):
            nonce = enc_val[3:15]
            ciphertext = enc_val[15:-16]
            tag = enc_val[-16:]
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
            except Exception as e:
                print(f'  {name} v10/v11 解密失败: {e}')
                continue
        
        # 旧格式: DPAPI 直接加密
        else:
            try:
                decrypted = win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1].decode('utf-8', errors='replace')
            except Exception as e:
                print(f'  {name} DPAPI 解密失败: {e}')
                continue
        
        if decrypted:
            cookies[name] = decrypted
            # 只打印前几个字符
            preview = decrypted[:20] + '...' if len(decrypted) > 20 else decrypted
            print(f'  ✓ {name} = {preview} ({host_key})')
    
    conn.close()
    
    # 清理
    try:
        shutil.rmtree(tmp)
    except:
        pass
    
    return cookies


def get_following_list(cookies):
    """调用 B 站 API 获取关注列表"""
    # 先获取自己的 mid
    nav_url = "https://api.bilibili.com/x/web-interface/nav"
    
    cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/',
        'Cookie': cookie_str,
    }
    
    req = urllib.request.Request(nav_url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f'获取用户信息失败: {e}')
        return None
    
    if data.get('code') != 0:
        print(f'获取用户信息失败: code={data.get("code")}, message={data.get("message")}')
        return None
    
    mid = data['data']['mid']
    uname = data['data']['uname']
    print(f'\n当前登录用户: {uname} (MID: {mid})')
    
    # 获取关注列表
    all_following = []
    total = 0
    page = 1
    ps = 50
    
    while True:
        follow_url = f'https://api.bilibili.com/x/relation/followings?vmid={mid}&pn={page}&ps={ps}&order=desc&order_type=attention'
        req2 = urllib.request.Request(follow_url, headers=headers)
        
        try:
            with urllib.request.urlopen(req2, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f'获取关注列表失败 (第{page}页): {e}')
            break
        
        if data.get('code') != 0:
            print(f'获取关注列表失败: {data.get("message")}')
            break
        
        list_data = data['data']['list']
        total = data['data']['total']
        all_following.extend(list_data)
        
        print(f'  已获取 {len(all_following)}/{total} 个关注')
        
        if len(all_following) >= total or not list_data:
            break
        page += 1
        import time
        time.sleep(0.3)
    
    return all_following


def main():
    # 1. 解密 cookies
    print('=' * 50)
    print('正在从 Edge 解密 B 站 Cookies...')
    print('=' * 50)
    
    cookies = get_bilibili_cookies()
    if not cookies:
        print('\n错误: 未能获取到有效的 B 站 Cookie！')
        print('请确保：')
        print('  1. Edge 浏览器已完全关闭')
        print('  2. 你已在 Edge 中登录了 B 站')
        sys.exit(1)
    
    # 检查关键 cookie
    key_cookies = ['SESSDATA', 'bili_jct', 'DedeUserID']
    missing = [k for k in key_cookies if k not in cookies]
    if missing:
        print(f'\n警告: 缺少关键 Cookie: {missing}')
        print('可能无法正常访问需要登录的 API')
    
    # 2. 获取关注列表
    print('\n' + '=' * 50)
    print('正在获取 B 站关注列表...')
    print('=' * 50)
    
    following = get_following_list(cookies)
    if following is None:
        sys.exit(1)
    
    # 3. 输出结果
    print(f'\n=== 共关注 {len(following)} 个 UP 主 ===')
    for i, up in enumerate(following[:20], 1):
        print(f'  {i}. {up["uname"]} (MID: {up["mid"]})')
    
    if len(following) > 20:
        print(f'  ... 还有 {len(following) - 20} 个')
    
    # 4. 保存到文件
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bili_following.json')
    result = []
    for up in following:
        result.append({
            'name': up['uname'],
            'mid': str(up['mid']),
            'avatar': up.get('face', ''),
            'sign': up.get('sign', ''),
        })
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f'\n关注列表已保存到: {output_file}')


if __name__ == '__main__':
    main()
