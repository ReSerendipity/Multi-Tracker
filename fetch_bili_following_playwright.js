/**
 * 复制 Edge 用户数据到临时目录（Edge 已关闭，文件未锁定）
 * 然后用 Playwright 启动获取 B 站关注列表
 */
const { chromium } = require('playwright');
const path = require('path');
const os = require('os');
const fs = require('fs');

const edgeExe = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const defaultUserDataDir = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data');
const tempUserDataDir = path.join(os.tmpdir(), 'edge-bili-follow-' + Date.now());
const API_BASE = 'https://api.bilibili.com';

function copyDirSync(src, dest) {
  if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    try {
      if (entry.isDirectory()) {
        copyDirSync(srcPath, destPath);
      } else {
        fs.copyFileSync(srcPath, destPath);
      }
    } catch (e) {
      console.error(`  跳过: ${entry.name} - ${e.message}`);
    }
  }
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  let context;
  try {
    // 1. 复制用户数据到临时目录
    console.error('正在复制 Edge 用户配置到临时目录...');
    console.error(`  源: ${defaultUserDataDir}`);
    console.error(`  目标: ${tempUserDataDir}`);
    
    // 只复制关键目录：Default 和 Local State
    fs.mkdirSync(tempUserDataDir, { recursive: true });
    
    // 复制 Local State
    const localStateSrc = path.join(defaultUserDataDir, 'Local State');
    const localStateDst = path.join(tempUserDataDir, 'Local State');
    if (fs.existsSync(localStateSrc)) {
      fs.copyFileSync(localStateSrc, localStateDst);
      console.error('  已复制: Local State');
    }
    
    // 复制 Default 目录（包含 Cookies、Login Data 等）
    const defaultDir = path.join(defaultUserDataDir, 'Default');
    const tempDefaultDir = path.join(tempUserDataDir, 'Default');
    
    // 先列出 Default 下的文件，选择性复制（大目录如 Cache 跳过）
    const skipDirs = new Set([
      'Cache', 'Code Cache', 'GPUCache', 'Service Worker',
      'IndexedDB', 'Local Storage', 'Session Storage',
      'Application Cache', 'DawnCache', 'ShaderCache',
      'Storage', 'WebStorage', 'File System', 'databases',
    ]);
    const skipFiles = new Set([
      'Cookies-journal', 'Favicons', 'History', 'History-journal',
      'Visited Links', 'Top Sites', 'Shortcuts',
    ]);
    
    function copySelective(srcDir, dstDir, depth = 0) {
      if (!fs.existsSync(srcDir)) return;
      fs.mkdirSync(dstDir, { recursive: true });
      
      const entries = fs.readdirSync(srcDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          if (skipDirs.has(entry.name)) continue;
          if (depth > 2) continue; // 限制深度
          copySelective(
            path.join(srcDir, entry.name),
            path.join(dstDir, entry.name),
            depth + 1
          );
        } else {
          if (skipFiles.has(entry.name)) continue;
          try {
            fs.copyFileSync(
              path.join(srcDir, entry.name),
              path.join(dstDir, entry.name)
            );
          } catch (e) {
            // 跳过锁定的文件
          }
        }
      }
    }
    
    copySelective(defaultDir, tempDefaultDir);
    console.error('  已复制: Default 目录（关键文件）');
    
    // 验证 Cookies 文件是否复制成功
    const cookieFile = path.join(tempDefaultDir, 'Network', 'Cookies');
    const cookieFileOld = path.join(tempDefaultDir, 'Cookies');
    if (fs.existsSync(cookieFile)) {
      console.error(`  Cookies 文件大小: ${fs.statSync(cookieFile).size} bytes (Network/Cookies)`);
    } else if (fs.existsSync(cookieFileOld)) {
      console.error(`  Cookies 文件大小: ${fs.statSync(cookieFileOld).size} bytes (旧位置)`);
    } else {
      console.error('  警告: 未找到 Cookies 文件！');
    }

    // 2. 启动 Edge
    console.error('\n正在启动 Edge...');
    context = await chromium.launchPersistentContext(tempUserDataDir, {
      executablePath: edgeExe,
      headless: true,
      timeout: 30000,
      args: [
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions',
        '--disable-gpu',
        '--disable-sync',
      ],
    });

    const page = context.pages()[0] || await context.newPage();

    // 3. 获取登录状态
    console.error('正在获取 B 站登录状态...');
    const navResp = await page.goto(`${API_BASE}/x/web-interface/nav`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000,
    });
    const navData = await navResp.json();
    
    if (navData.code !== 0) {
      console.error(`未登录！code=${navData.code}, message=${navData.message}`);
      throw new Error('Bilibili not logged in');
    }

    const myUid = navData.data.mid;
    const myName = navData.data.uname;
    console.error(`登录成功: ${myName} (UID: ${myUid})`);

    // 4. 分页获取所有关注
    const allFollowings = [];
    let pn = 1;
    const ps = 50;
    let total = 0;

    while (true) {
      console.error(`正在获取关注列表 (第 ${pn} 页)...`);
      const url = `${API_BASE}/x/relation/followings?vmid=${myUid}&pn=${pn}&ps=${ps}&order=desc&order_type=attention`;
      const resp = await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: 15000,
      });
      const data = await resp.json();
      
      if (data.code !== 0) {
        throw new Error(`关注列表 API 失败: ${JSON.stringify(data)}`);
      }

      total = data.data.total;
      const list = data.data.list || [];
      if (list.length === 0) break;

      for (const item of list) {
        allFollowings.push({
          mid: String(item.mid),
          uname: item.uname,
          face: item.face || '',
          sign: item.sign || '',
        });
      }

      console.error(`  已获取 ${allFollowings.length}/${total} 个关注`);

      if (allFollowings.length >= total) break;
      pn++;
      await sleep(300);
    }

    // 5. 输出结果
    console.log(JSON.stringify({
      user: { mid: String(myUid), uname: myName },
      total: total,
      followings: allFollowings,
    }, null, 2));

    console.error(`\n完成！共导出 ${allFollowings.length} 个关注的 UP 主。`);

    await context.close();

  } catch (err) {
    console.error(`错误: ${err.message}`);
    if (context) {
      try { await context.close(); } catch (e) {}
    }
    process.exit(1);
  } finally {
    // 清理临时目录（可选，先保留方便调试）
    // try { fs.rmSync(tempUserDataDir, { recursive: true, force: true }); } catch (e) {}
  }
})();
