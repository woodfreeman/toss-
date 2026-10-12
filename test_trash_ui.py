# -*- coding: utf-8 -*-
"""Toss v0.1.3 回收站 UI 实测（playwright）。结果逐条落盘 test_trash_ui_progress.txt。"""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8423"
PROG = Path(__file__).resolve().parent / "test_trash_ui_progress.txt"
out = PROG.open("w", encoding="utf-8")


def log(m):
    out.write(m + "\n")
    out.flush()


def step(n, name, ok, detail=""):
    log(f"[{'PASS' if ok else 'FAIL'}] {n}. {name}" + (f" — {detail}" if detail else ""))


fails = 0
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-proxy-server"])
    pg = b.new_page()
    pg.goto(BASE, wait_until="domcontentloaded")

    # 0. 预清理：清空回收站（防上次运行残留污染断言）
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r0 = opener.open(urllib.request.Request(BASE + "/api/trash/empty", method="POST"), b"")
    log(f"[PRE] 回收站清空: {r0.read().decode()}")

    # 1. 页面加载，回收站按钮存在
    pg.wait_for_selector("#btnTrashView")
    step(1, "页面加载、回收站入口存在", True)

    # 2. 发一条文本
    marker = "UI回收站测试" + str(int(__import__("time").time()))
    pg.fill("#textContent", marker)
    pg.click("#btnSendText")
    pg.wait_for_function(
        f"document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    step(2, "发送文本并出现在记录列表", True, marker)

    # 3. 点 🗑 软删除 → 从列表消失
    item = pg.locator(".item", has_text=marker).first
    item.locator("button[data-act=del]").click()
    pg.wait_for_function(
        f"!document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    step(3, "点垃圾桶后条目从记录列表消失", True)
    n0 = pg.locator("#itemList .item").count()

    # 4. 切到回收站 → 条目出现，带还原/彻底删除按钮，显示删除时间
    pg.click("#btnTrashView")
    pg.wait_for_function(
        f"document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    body_text = pg.locator("#itemList").inner_text()
    titem = pg.locator(".item", has_text=marker).first
    has_restore = titem.locator("button[data-act=restore]").count() == 1
    has_purge = titem.locator("button[data-act=purge]").count() == 1
    title_ok = "回收站" in pg.locator("#listTitle").inner_text()
    del_time = "删除于" in body_text
    ok = has_restore and has_purge and title_ok and del_time
    fails += 0 if ok else 1
    step(4, "回收站视图：还原/彻底删除按钮+删除时间+标题", ok,
         f"restore={has_restore} purge={has_purge} title={title_ok} delTime={del_time}")

    # 5. 还原 → 回收站变空
    titem.locator("button[data-act=restore]").click()
    pg.wait_for_function(
        f"!document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    box_txt = pg.locator("#itemList").inner_text()
    ok = "回收站是空的" in box_txt
    if not ok:
        log(f"[DBG] 还原后列表: {box_txt!r} 标题={pg.locator('#listTitle').inner_text()!r}")
    fails += 0 if ok else 1
    step(5, "还原后回收站为空", ok)

    # 6. 返回记录视图 → 条目回来了
    pg.click("#btnTrashView")
    pg.wait_for_function(
        f"document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    title_ok = "传输记录" in pg.locator("#listTitle").inner_text()
    empty_btn_hidden = pg.locator("#btnEmptyTrash").is_hidden()
    ok = title_ok and empty_btn_hidden
    step(6, "返回记录视图条目恢复、清空按钮隐藏", ok,
         f"title={title_ok} emptyBtnHidden={empty_btn_hidden}")

    # 7. 软删除 → 进回收站 → 彻底删除 → 两侧都消失
    pg.locator(".item", has_text=marker).first.locator("button[data-act=del]").click()
    pg.wait_for_function(
        f"!document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    pg.click("#btnTrashView")
    pg.wait_for_function(
        f"document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    pg.once("dialog", lambda d: d.accept())
    pg.locator(".item", has_text=marker).first.locator("button[data-act=purge]").click()
    pg.wait_for_function(
        f"!document.querySelector('#itemList').innerText.includes('{marker}')",
        timeout=8000,
    )
    ok = "回收站是空的" in pg.locator("#itemList").inner_text()
    fails += 0 if ok else 1
    step(7, "软删→回收站→彻底删除全链路", ok)

    log(f"=== 完成：{7 - fails}/7 PASS ===")
    out.close()
    print(f"done: {7 - fails}/7 PASS")
    # 不调 b.close()：已知挂住会话，进程退出即清理
    import os
    os._exit(0)
