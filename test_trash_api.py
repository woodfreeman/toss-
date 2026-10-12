# -*- coding: utf-8 -*-
"""Toss v0.1.3 回收站 API 实测。结果逐条落盘 test_trash_progress.txt。"""
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8423"
PROG = Path(__file__).resolve().parent / "test_trash_progress.txt"
FILES_DIR = Path(__file__).resolve().parent / "data" / "files"
out = PROG.open("w", encoding="utf-8")

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(msg):
    out.write(msg + "\n")
    out.flush()


def req(method, path, data=None, raw=False):
    r = urllib.request.Request(BASE + path, method=method)
    body = None
    if data is not None and isinstance(data, dict):
        body = json.dumps(data).encode()
        r.add_header("Content-Type", "application/json")
    elif data is not None:
        body = data
    try:
        with opener.open(r, body) as resp:
            b = resp.read()
            return resp.status, (b if raw else json.loads(b))
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, b


def step(n, name, ok, detail=""):
    log(f"[{'PASS' if ok else 'FAIL'}] {n}. {name}" + (f" — {detail}" if detail else ""))
    return ok


fails = 0

# 1. 造两条文本
s, a = req("POST", "/api/text", {"content": "回收站测试A " + uuid.uuid4().hex[:6]})
s2, b = req("POST", "/api/text", {"content": "回收站测试B " + uuid.uuid4().hex[:6]})
ok = s == 200 and s2 == 200 and a.get("id") and b.get("id")
fails += not step(1, "造两条文本", ok, f"A={a.get('id')} B={b.get('id')}")
A, B = a["id"], b["id"]

# 2. 软删除 A
s, r = req("DELETE", f"/api/items/{A}")
ok = s == 200 and r.get("ok")
fails += not step(2, "DELETE 软删除 A", ok, json.dumps(r, ensure_ascii=False))

# 3. /api/items 不含 A，仍含 B
s, items = req("GET", "/api/items?limit=500")
ids = {x["id"] for x in items}
ok = s == 200 and A not in ids and B in ids
fails += not step(3, "记录列表不含 A、仍含 B", ok, f"items={len(items)}")

# 4. /api/trash 含 A 且 deleted_at 非空
s, trash = req("GET", "/api/trash?limit=500")
row = next((x for x in trash if x["id"] == A), None)
ok = s == 200 and row and row["deleted_at"] and time.time() - row["deleted_at"] < 60
fails += not step(4, "回收站含 A（deleted_at 刚写入）", ok,
                  f"trash={len(trash)} deleted_at={row['deleted_at'] if row else None}")

# 5. 还原 A
s, r = req("POST", f"/api/items/{A}/restore")
s2, items = req("GET", "/api/items?limit=500")
s3, trash = req("GET", "/api/trash?limit=500")
ok = (s == 200 and A in {x["id"] for x in items}
      and A not in {x["id"] for x in trash})
fails += not step(5, "还原 A 回记录列表", ok, json.dumps(r, ensure_ascii=False))

# 6. 文件条目软删除后文件仍在磁盘
png = Path(__file__).resolve().parent / "_trash_test.png"
png.write_bytes(bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d4944415478da63fcffff3f0300050201" "48bdd28"
    "00000000049454e44ae426082"))
boundary = "----tossboundary"
with png.open("rb") as f:
    payload = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
        f"filename=\"trash-test.png\"\r\nContent-Type: image/png\r\n\r\n"
    ).encode() + f.read() + f"\r\n--{boundary}--\r\n".encode()
s, r = req("POST", "/api/files",
           data=payload)  # Content-Type 修正
# 手动补 multipart 头重发
r2 = urllib.request.Request(BASE + "/api/files", method="POST")
r2.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
with opener.open(r2, payload) as resp:
    up = json.loads(resp.read())
fid = up["saved"][0]["id"]

s, items = req("GET", "/api/items?limit=500")
frow = next(x for x in items if x["id"] == fid)
stored = frow["stored_name"]
p = FILES_DIR / stored
ok = p.exists()
fails += not step(6, "文件条目已上传且文件在磁盘", ok, f"stored={stored}")

req("DELETE", f"/api/items/{fid}")
ok = p.exists()
fails += not step(7, "软删除后文件仍在磁盘（可还原）", ok)

# 8. 彻底删除 → 文件被物理清除
s, r = req("DELETE", f"/api/trash/{fid}")
ok = s == 200 and not p.exists()
fails += not step(8, "彻底删除后文件物理清除", ok,
                  f"status={s} exists={p.exists()}")

# 9. 清空回收站
req("DELETE", f"/api/items/{A}")  # A 再进回收站
s, r = req("POST", "/api/trash/empty")
s2, trash = req("GET", "/api/trash?limit=500")
ok = s == 200 and r.get("removed", 0) >= 1 and len(trash) == 0
fails += not step(9, "清空回收站", ok,
                  f"removed={r.get('removed')} 剩={len(trash)}")

# 10. /api/info 带 trash_count
s, info = req("GET", "/api/info")
ok = s == 200 and "trash_count" in info and info["version"] == "0.1.3"
fails += not step(10, "/api/info 含 trash_count 且版本 0.1.3", ok,
                  f"v={info.get('version')} trash_count={info.get('trash_count')}")

# 11. purge 不在回收站的条目应 400
s, r = req("DELETE", f"/api/trash/{B}")
ok = s == 400
fails += not step(11, "对未删除条目 purge 返回 400", ok, f"status={s}")

# 收尾：清掉测试条目
for x in [A, B]:
    req("DELETE", f"/api/items/{x}")
req("POST", "/api/trash/empty")

log(f"=== 完成：{11 - fails}/11 PASS, {fails} FAIL ===")
out.close()
print(f"done: {11 - fails}/11 PASS, {fails} FAIL")
