# -*- coding: utf-8 -*-
"""Toss v0.1.2 粘贴图片实测：合成 paste 事件（图片 → 自动上传；文本 → 不受影响）"""
import os
import tempfile
import time
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

prog("=== start paste test ===")
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

    # 1) 合成粘贴图片事件（canvas 生成真 png → DataTransfer → paste 事件）
    page.evaluate("""
      () => new Promise((resolve) => {
        const c = document.createElement("canvas");
        c.width = 120; c.height = 80;
        const ctx = c.getContext("2d");
        ctx.fillStyle = "#0d9488"; ctx.fillRect(0, 0, 120, 80);
        c.toBlob((blob) => {
          const dt = new DataTransfer();
          dt.items.add(new File([blob], "paste-shot.png", {type: "image/png"}));
          const ev = new Event("paste", {bubbles: true, cancelable: true});
          Object.defineProperty(ev, "clipboardData", {value: dt});
          document.dispatchEvent(ev);
          resolve();
        }, "image/png");
      })
    """)
    prog("paste image dispatched")
    page.wait_for_function(
        f"document.querySelectorAll('.item').length === {n0 + 1}", timeout=10000)
    n1 = page.locator(".item").count()
    check("粘贴图片自动上传并出现在列表", n1 == n0 + 1, f"{n0} -> {n1}")
    check("新条目是图片(缩略图渲染)", page.locator(".item-img").count() >= 1)
    tab_active = page.locator(".tab.active").get_attribute("data-tab")
    check("粘贴后自动切到文件页签", tab_active == "file", f"active={tab_active}")

    # 2) 文本粘贴不被拦截（合成事件无法触发浏览器默认插入，改为验证
    #    handler 未对纯文本 paste 调 preventDefault —— 即不干扰默认行为）
    not_prevented = page.evaluate("""
      () => {
        const ta = document.querySelector("#textContent");
        ta.focus();
        const dt = new DataTransfer();
        dt.setData("text/plain", "纯文本粘贴不受影响");
        const ev = new Event("paste", {bubbles: true, cancelable: true});
        Object.defineProperty(ev, "clipboardData", {value: dt});
        ta.dispatchEvent(ev);
        return !ev.defaultPrevented;
      }
    """)
    check("纯文本粘贴未被拦截(defaultPrevented=false)", not_prevented is True)

    # 3) 文本粘贴不应产生新条目
    n2 = page.locator(".item").count()
    check("文本粘贴不触发上传", n2 == n1, f"{n1} -> {n2}")

    b.close()

ok = sum(1 for _, c, _ in results if c)
out = "\n".join(("PASS " if c else "FAIL ") + n + ((" | " + d) if d else "") for n, c, d in results)
out += f"\nSUMMARY: {ok}/{len(results)} passed"
prog(out)
with open(PROG, "w", encoding="utf-8") as f:
    f.write(out + "\n")
