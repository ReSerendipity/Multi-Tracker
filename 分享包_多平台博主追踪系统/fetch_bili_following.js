/**
 * 复制 Edge 用户数据到临时目录，再启动调试模式获取 B 站关注列表
 */
const { chromium } = require('playwright');
const path = require('path');
const os = require('os');
const fs = require('fs');

const edgeExe = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const defaultUserDataDir = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data');
const tempUserDataDir = path.join(os.tmpdir(), 'edge-debug-profile-' + Date.now());
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
      // 跳过被锁定的文件（如 Cookies 数据库）
    }
  }
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  let browser;
  try {
    console.error(`Copying Edge user data to temp dir...`);
    console.error(`  From: ${defaultUserDataDir}`);
    console.error(`  To:   ${tempUserDataDir}`);

    // 只复制 Default 配置文件和 Cookie 相关文件
    const defaultDir = path.join(defaultUserDataDir, 'Default');
    const tempDefaultDir = path.join(tempUserDataDir, 'Default');
    
    // 创建目录结构
    fs.mkdirSync(tempDefaultDir, { recursive: true });

    // 复制关键文件（Cookies, Login Data, Local Storage 等）
    const filesToCopy = [
      'Cookies',
      'Cookies-journal',
      'Login Data',
      'Login Data For Account',
      'Preferences',
      'Local State',
    ];

    for (const file of filesToCopy) {
      const src = path.join(defaultDir, file);
      const dst = path.join(tempDefaultDir, file);
      if (fs.existsSync(src)) {
        try {
          fs.copyFileSync(src, dst);
          console.error(`  Copied: ${file}`);
        } catch (e) {
          console.error(`  Skipped (locked): ${file}`);
        }
      }
    }

    // 复制 Local State
    const localStateSrc = path.join(defaultUserDataDir, 'Local State');
    const localStateDst = path.join(tempUserDataDir, 'Local State');
    if (fs.existsSync(localStateSrc)) {
      try {
        fs.copyFileSync(localStateSrc, localStateDst);
        console.error('  Copied: Local State');
      } catch (e) {
        console.error('  Skipped: Local State (locked)');
      }
    }

    console.error('Launching Edge with temp profile...');
    browser = await chromium.launchPersistentContext(tempUserDataDir, {
      executablePath: edgeExe,
      headless: true,
      timeout: 30000,
    });

    const page = browser.pages()[0] || await browser.newPage();

    // 获取当前登录用户信息
    console.error('Fetching user info...');
    const navResp = await page.goto(`${API_BASE}/x/web-interface/nav`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    const navData = await navResp.json();
    if (navData.code !== 0) {
      console.error(`Not logged in! code=${navData.code}, message=${navData.message}`);
      console.error('Cookie import may have failed due to Windows DPAPI encryption.');
      throw new Error('Bilibili not logged in');
    }

    const myUid = navData.data.mid;
    const myName = navData.data.uname;
    console.error(`Logged in as: ${myName} (UID: ${myUid})`);

    // 分页获取所有关注
    const allFollowings = [];
    let pn = 1;
    const ps = 50;
    let total = 0;

    while (true) {
      console.error(`Fetching page ${pn}...`);
      const url = `${API_BASE}/x/relation/followings?vmid=${myUid}&pn=${pn}&ps=${ps}&order=desc`;
      const resp = await page.goto(url, {
        waitUntil: 'networkidle',
        timeout: 15000,
      });
      const data = await resp.json();
      if (data.code !== 0) throw new Error(`followings API failed: ${JSON.stringify(data)}`);

      total = data.data.total;
      const list = data.data.list || [];
      if (list.length === 0) break;

      for (const item of list) {
        allFollowings.push({
          mid: item.mid,
          uname: item.uname,
          mtime: item.mtime,
          official: item.official_verify?.desc || '',
          vip: item.vip?.nickname_color ? '大会员' : '',
        });
      }

      console.error(`  Got ${allFollowings.length}/${total} followings`);

      if (allFollowings.length >= total) break;
      pn++;
      await sleep(500);
    }

    const result = {
      user: { mid: myUid, uname: myName },
      total: total,
      followings: allFollowings,
    };
    console.log(JSON.stringify(result, null, 2));
    console.error(`\nDone! Total: ${allFollowings.length} followings exported.`);

    await browser.close();

  } catch (err) {
    console.error(`Error: ${err.message}`);
    if (browser) await browser.close();
    process.exit(1);
  }
})();
