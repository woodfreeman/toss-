# -*- coding: utf-8 -*-
"""Toss v0.1.1 前端行为实测：复制 fallback + 长文本折叠展开"""
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = os.environ.get("TOSS_TEST_BASE_URL", "").rstrip("/")
parsed_base = urlparse(BASE)
if (
    parsed_base.scheme != "http"
    or not parsed_base.hostname
    or parsed_base.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
):
    raise SystemExit(
        "Set TOSS_TEST_BASE_URL to a reachable, non-loopback HTTP URL for the test server."
    )

PROG = Path(tempfile.gettempdir()) / f"{Path(__file__).stem}-progress.txt"
def prog(msg):
    with open(PROG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    prog(("PASS " if cond else "FAIL ") + name)

prog("=== start ===")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-proxy-server"])
    ctx = b.new_context()
    page = ctx.new_page()
    page.set_default_timeout(15000)
    prog("goto...")
    page.goto(BASE + "/", wait_until="domcontentloaded")
    prog("goto done, wait copy btn")
    page.wait_for_selector('button[data-act="copy"]', timeout=15000)
    prog("copy btn found")

    check("不安全上下文(isSecureContext=False)", page.evaluate("window.isSecureContext") is False)
    check("navigator.clipboard 不存在(复现原bug前提)", page.evaluate("navigator.clipboard === undefined"))

    # 1) 复制按钮 → 应走 fallback 成功，toast 出现"已复制"
    first_copy = page.locator('button[data-act="copy"]').first
    first_copy.click()
    page.wait_for_timeout(400)
    toast_txt = page.locator("#toastBox").inner_text()
    check("复制按钮(fallback)成功", "已复制" in toast_txt, f"toast={toast_txt.strip()!r}")

    # 2) 长文本卡片应有"展开"按钮
    toggles = page.locator('button[data-act="toggle"]')
    n_toggle = toggles.count()
    check("长文本卡片出现展开按钮", n_toggle >= 1, f"toggle数={n_toggle}")

    if n_toggle >= 1:
        t = toggles.first
        item = t.locator("xpath=ancestor::div[@class='item']")
        txt = item.locator(".item-text")
        h_before = txt.bounding_box()["height"]
        t.click()
        page.wait_for_timeout(200)
        h_after = txt.bounding_box()["height"]
        check("展开后高度变大", h_after > h_before, f"{h_before:.0f}px -> {h_after:.0f}px")
        check("展开后按钮变收起", t.inner_text().strip().startswith("收起"), f"btn={t.inner_text().strip()!r}")
        t.click()
        page.wait_for_timeout(200)
        h_back = txt.bounding_box()["height"]
        check("再点收起恢复折叠", abs(h_back - h_before) < 4, f"{h_back:.0f}px")

    # 3) 短文本卡片不应有展开按钮(用最后一张含'短文本'的卡)
    short_items = page.locator(".item", has_text="短文本").filter(has=page.locator(".item-text"))
    if short_items.count() >= 1:
        n_btn = short_items.first.locator('button[data-act="toggle"]').count()
        check("短文本卡片无展开按钮", n_btn == 0, f"toggle数={n_btn}")

    b.close()

fails = [r for r in results if not r[1]]
lines = []
for name, ok, d in results:
    lines.append(("PASS" if ok else "FAIL") + " " + name + ((" | " + d) if d else ""))
lines.append(f"SUMMARY: {len(results)-len(fails)}/{len(results)} passed")
out = "\n".join(lines)
print(out, flush=True)
with open(PROG, "w", encoding="utf-8") as f:
    f.write(out + "\n")
sys.exit(1 if fails else 0)
