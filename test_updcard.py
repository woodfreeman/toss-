# -*- coding: utf-8 -*-
"""v0.1.5 版本徽章回看更新说明 UI 实测。结果落盘 test_updcard_progress.txt。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8423"
PROG = Path(__file__).resolve().parent / "test_updcard_progress.txt"
out = PROG.open("w", encoding="utf-8")


def log(m):
    out.write(m + "\n")
    out.flush()


def step(n, name, ok, detail=""):
    log(f"[{'PASS' if ok else 'FAIL'}] {n}. {name}" + (f" — {detail}" if detail else ""))
    return ok


fails = 0
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-proxy-server"])
    pg = b.new_page()
    pg.goto(BASE, wait_until="domcontentloaded")
    pg.wait_for_function("document.querySelector('#verChip').textContent === 'v0.1.5'", timeout=8000)

    # 1. 首次打开：升级卡片只显示当前版本 1 节
    pg.wait_for_function("document.querySelector('#updMask').style.display === 'flex'", timeout=8000)
    n_ver = pg.locator("#updList .upd-ver").count()
    title = pg.locator("#updTitle").inner_text()
    ok = n_ver == 1 and "0.1.5" in title
    fails += not step(1, "升级卡片：标题+仅当前版本一节", ok, f"title={title} vers={n_ver}")
    pg.click("#btnUpdOk")

    # 2. 点版本徽章 → 全量更新说明（5 个版本，新→旧）
    pg.click("#verChip")
    pg.wait_for_function("document.querySelector('#updMask').style.display === 'flex'", timeout=8000)
    n_ver = pg.locator("#updList .upd-ver").count()
    title = pg.locator("#updTitle").inner_text()
    first = pg.locator("#updList .upd-ver").first.inner_text()
    last = pg.locator("#updList .upd-ver").last.inner_text()
    ok = n_ver == 5 and title == "📜 更新说明" and first == "v0.1.5" and last == "v0.1.1"
    fails += not step(2, "点徽章弹全量说明（5 版本新→旧）", ok,
                      f"title={title} vers={n_ver} first={first} last={last}")

    # 3. 知道了关闭
    pg.click("#btnUpdOk")
    ok = pg.evaluate("document.querySelector('#updMask').style.display") == "none"
    fails += not step(3, "知道了关闭", ok)

    # 4. 刷新后升级卡不再弹
    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_function("document.querySelector('#verChip').textContent === 'v0.1.5'", timeout=8000)
    pg.wait_for_timeout(1000)
    ok = pg.evaluate("document.querySelector('#updMask').style.display") == "none"
    fails += not step(4, "刷新后升级卡不再弹", ok)

    # 5. 已看过状态点徽章仍可回看
    pg.click("#verChip")
    ok = pg.evaluate("document.querySelector('#updMask').style.display") == "flex"
    fails += not step(5, "已看过状态下徽章仍可回看", ok)

    log(f"=== 完成：{5 - fails}/5 PASS ===")
    out.close()
    print(f"done: {5 - fails}/5 PASS")
    import os
    os._exit(0)
