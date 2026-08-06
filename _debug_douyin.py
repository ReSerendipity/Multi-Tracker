"""诊断抖音页面结构"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CDP_PORT = 9333

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    context = browser.contexts[0]
    page = context.new_page()
    
    print("打开抖音首页...")
    page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    
    # 截图
    screenshot_path = ROOT / "douyin_home.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"截图保存: {screenshot_path}")
    
    # 打印页面标题
    print(f"页面标题: {page.title()}")
    
    # 查找所有包含 /user/ 的链接
    users = page.evaluate("""() => {
        const links = document.querySelectorAll('a[href*="/user/"]');
        const results = [];
        for (const a of links) {
            results.push({
                href: a.href,
                text: (a.textContent || '').trim().slice(0, 50),
                class: a.className ? String(a.className).slice(0, 100) : '',
            });
        }
        return results.slice(0, 20);
    }""")
    
    print(f"\n找到 {len(users)} 个用户链接:")
    for u in users[:10]:
        print(f"  {u['href'][:80]}")
        print(f"    text: {u['text']}")
        print(f"    class: {u['class'][:60]}")
    
    # 搜索
    print("\n尝试搜索...")
    page.goto("https://www.douyin.com/search/科技?type=user", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    
    screenshot2 = ROOT / "douyin_search.png"
    page.screenshot(path=str(screenshot2), full_page=True)
    print(f"搜索截图: {screenshot2}")
    
    # 查看搜索结果结构
    search_html = page.evaluate("""() => {
        const body = document.body.innerHTML;
        return body.slice(0, 3000);
    }""")
    print(f"搜索页面前3000字符:\n{search_html}")
    
    page.close()
    browser.close()
