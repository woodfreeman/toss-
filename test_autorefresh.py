# -*- coding: utf-8 -*-
"""Toss 自动刷新实测：开页面 -> 外部注入新文本 -> 5s 轮询自动出现 + toast 提示"""
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

def post_text(page, content):
    return page.evaluate("""async (content) => {
        const r = await fetch('/api/text', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({content})
        });
        return await r.json();
    }""", content)

prog("=== start autorefresh test ===")
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    prog(("PASS " if cond else "FAIL ") + name + ((" | " + detail) if detail else ""))

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-proxy-server"])
    page = b.new_context().new_page()
    page.set_default_timeout(15000)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_selector('button[data-act="copy"]', timeout=15000)
    prog("page loaded")

    n0 = page.locator(".item").count()
    prog(f"initial items={n0}")

    needle = "自动刷新测试条目-" + str(int(time.time()))
    r = post_text(page, needle)
    prog("injected")
    check("外部注入成功", r.get("ok") is True)

    # 等自动刷新生效（5s 轮询 + 余量）
    page.wait_for_selector(f".item:has-text('{needle}')", timeout=10000)
    n1 = page.locator(".item").count()
    check("新条目自动出现(无需F5)", n1 == n0 + 1, f"{n0} -> {n1}")
    toast_txt = page.locator("#toastBox").inner_text()
    check("toast 提示新记录", "新记录" in toast_txt, f"toast={toast_txt.strip()!r}")

    # 无变化周期不应重渲染：再等 6s，条目数不变
    time.sleep(6)
    n2 = page.locator(".item").count()
    check("无变化周期不误刷新", n2 == n1, f"{n1} -> {n2}")

    b.close()

ok = sum(1 for _, c, _ in results if c)
out = "\n".join(("PASS " if c else "FAIL ") + n + ((" | " + d) if d else "") for n, c, d in results)
out += f"\nSUMMARY: {ok}/{len(results)} passed"
prog(out)
with open(PROG, "w", encoding="utf-8") as f:
    f.write(out + "\n")
