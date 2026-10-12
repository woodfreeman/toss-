# -*- coding: utf-8 -*-
"""v0.1.4 自更新 API 开发模式实测。结果落盘 test_update_api_progress.txt。"""
import json
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8423"
PROG = Path(__file__).resolve().parent / "test_update_api_progress.txt"
out = PROG.open("w", encoding="utf-8")


def log(m):
    out.write(m + "\n")
    out.flush()


def step(n, name, ok, detail=""):
    log(f"[{'PASS' if ok else 'FAIL'}] {n}. {name}" + (f" — {detail}" if detail else ""))
    return ok


def req(method, path, data=None, headers=None):
    r = urllib.request.Request(BASE + path, method=method)
    body = None
    if data is not None and isinstance(data, dict):
        body = json.dumps(data).encode()
        r.add_header("Content-Type", "application/json")
    elif data is not None:
        body = data
    if headers:
        for k, v in headers.items():
            r.add_header(k, v)
    try:
        with opener.open(r, body, timeout=60) as resp:
            raw = resp.read()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw.decode("utf-8", "replace")
            return resp.status, dict(resp.headers), parsed
    except urllib.error.HTTPError as e:
        try:
            return e.code, dict(e.headers), json.loads(e.read())
        except Exception:
            return e.code, dict(e.headers), {}


opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
fails = 0


def hget(hdrs, name):
    for k, v in hdrs.items():
        if k.lower() == name.lower():
            return v
    return None


# 0. 预清理：删掉上轮运行可能残留的 Toss-v*.exe 条目
s, _, items = req("GET", "/api/items?limit=500")
for it in items:
    if (it.get("orig_name") or "").lower().startswith("toss-v") and it.get("orig_name", "").lower().endswith(".exe"):
        req("DELETE", f"/api/items/{it['id']}")
req("POST", "/api/trash/empty")
log("[PRE] 残留升级包已清理")

# 1. check 初始无更新
s, _, r = req("GET", "/api/update/check")
ok = s == 200 and r["available"] is False and r["version"] == "0.1.4"
fails += not step(1, "check 初始 available=False, version=0.1.4", ok, json.dumps(r, ensure_ascii=False))

# 2. 上传假升级包 Toss-v9.9.9.exe（内容随便，非 exe 也能测命名识别）
payload = b"fake-update-payload-for-naming-test"
boundary = "----b" + uuid.uuid4().hex[:8]
body = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
    f"filename=\"Toss-v9.9.9.exe\"\r\nContent-Type: application/octet-stream\r\n\r\n"
).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
s, _, r = req("POST", "/api/files", data=body,
              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
fake_id = r["saved"][0]["id"]
ok = s == 200
fails += not step(2, "上传假升级包 Toss-v9.9.9.exe", ok, f"id={fake_id}")

# 3. check 识别到 9.9.9
s, _, r = req("GET", "/api/update/check")
ok = s == 200 and r["available"] is True and r["update_version"] == "9.9.9" and r["item_id"] == fake_id
fails += not step(3, "check 识别 9.9.9 为可更新", ok, json.dumps(r, ensure_ascii=False))

# 4. 开发模式 apply 被 400 拦截
s, _, r = req("POST", "/api/update/apply")
ok = s == 400
fails += not step(4, "开发模式 apply 返回 400（防误换包）", ok, f"status={s}")

# 5. 版本号低于当前的不算更新：上传 Toss-v0.0.1.exe
body2 = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
    f"filename=\"Toss-v0.0.1.exe\"\r\nContent-Type: application/octet-stream\r\n\r\n"
).encode() + b"old" + f"\r\n--{boundary}--\r\n".encode()
s, _, r = req("POST", "/api/files", data=body2,
              headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
old_id = r["saved"][0]["id"]
s, _, r = req("GET", "/api/update/check")
ok = r["update_version"] == "9.9.9"
fails += not step(5, "低版本包不触发更新提示", ok, f"still={r.get('update_version')}")

# 6. 静态资源 no-cache，API 不受影响
s, hdrs, _ = req("GET", "/")
ok = (hget(hdrs, "Cache-Control") or "") == "no-cache"
fails += not step(6, "静态首页 Cache-Control: no-cache", ok, str(hget(hdrs, "Cache-Control")))
s, hdrs, _ = req("GET", "/api/health")
ok = "no-cache" not in (hget(hdrs, "Cache-Control") or "")
fails += not step(7, "API 响应不受 no-cache 影响", ok)

# 收尾清理假包
req("DELETE", f"/api/items/{fake_id}")
req("DELETE", f"/api/items/{old_id}")
req("POST", "/api/trash/empty")
log(f"=== 完成：{7 - fails}/7 PASS ===")
out.close()
print(f"done: {7 - fails}/7 PASS")
