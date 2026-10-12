# -*- coding: utf-8 -*-
"""精确复现：python 分离 spawn Toss.exe + 父进程立即退出，观察子进程是否存活。"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import tempfile

EXE = Path(os.environ.get("TOSS_TEST_EXE", str(Path(__file__).with_name("Toss.exe"))))
out = Path(tempfile.gettempdir()) / "toss-detach-test.log"


def log(m):
    with out.open("a", encoding="utf-8") as f:
        f.write(m + "\n")


opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
env = dict(os.environ, TOSS_PORT="8427", TOSS_START_DELAY="3")
t0 = time.time()
p = subprocess.Popen([str(EXE)], cwd=str(EXE.parent), env=env, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
log(f"[{time.time()-t0:.1f}s] spawned pid={p.pid}")
os._exit(0)  # 模拟旧进程立即退出
