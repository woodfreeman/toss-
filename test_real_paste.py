# -*- coding: utf-8 -*-
"""真实剪贴板 + 真实 Ctrl+V 对测试服务器页面（headed）：诊断 + 验证"""
import json, os, tempfile, time, urllib.request
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = os.environ.get("TOSS_TEST_BASE_URL", "").rstrip("/")
parsed_base = urlparse(BASE)
if parsed_base.scheme != "http" or not parsed_base.hostname or parsed_base.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
    raise SystemExit("Set TOSS_TEST_BASE_URL to a reachable, non-loopback HTTP URL for the test server.")
PROG = Path(tempfile.gettempdir()) / f"{Path(__file__).stem}-progress.txt"
def prog(m):
    with open(PROG, "a", encoding="utf-8") as f:
        f.write(m + "\n")

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api_items():
    with _opener.open(BASE + "/api/items?limit=1", timeout=8) as r:
        return json.loads(r.read())

prog("=== start real-paste test ===")

n0_info = api_items()
n0_id = n0_info[0]["id"] if n0_info else "none"
prog(f"server top item before: {n0_id}")

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=["--no-proxy-server"])
    page = b.new_context(viewport={"width": 1100, "height": 800}).new_page()
    page.set_default_timeout(15000)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_selector('button[data-act="copy"]', timeout=15000)
    prog("test server page loaded")

    # 挂诊断监听：记录真实 paste事件的 clipboardData 形态
    page.evaluate("""
      () => {
        window.__pasteDump = [];
        document.addEventListener("paste", (e) => {
          const d = e.clipboardData;
          const rec = {files: [], items: [], text: (d.getData ? (()=>{try{return (d.getData("text/plain")||"").slice(0,50)}catch(_){return null}})() : null)};
          for (const f of (d.files || [])) rec.files.push({name: f.name, type: f.type, size: f.size});
          for (const it of (d.items || [])) rec.items.push({type: it.type, kind: it.kind});
          window.__pasteDump.push(rec);
        }, true);
      }
    """)
    prog("diagnostic listener armed")

    # 聚焦页面（点击标题区，不落在输入框）
    page.click(".logo-title")
    time.sleep(0.5)
    page.keyboard.press("Control+v")
    prog("Ctrl+V sent")
    time.sleep(6)

    dump = page.evaluate("window.__pasteDump")
    prog("pasteDump=" + json.dumps(dump, ensure_ascii=False))
    dom_count = page.locator(".item").count()
    prog(f"dom items after={dom_count}")

    b.close()

info = api_items()
top = info[0] if info else {}
prog(f"server top item after: {top.get('id')} name={top.get('orig_name')} size={top.get('size')}")
verdict = "PASTE_WORKED" if top.get("id") != n0_id else "NO_NEW_ITEM"
prog("VERDICT: " + verdict)
