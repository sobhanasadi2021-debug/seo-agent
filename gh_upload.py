# -*- coding: utf-8 -*-
"""Upload all git-tracked files to GitHub via Contents API using curl (VPN-safe)."""
import base64, json, os, subprocess, sys, tempfile

REPO = "sobhanasadi2021-debug/seo-agent"
cred = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                      capture_output=True, text=True).stdout
TOKEN = [l.split("=", 1)[1].strip() for l in cred.splitlines() if l.startswith("password=")][0]
API = f"https://api.github.com/repos/{REPO}/contents/"


def api(path, data=None):
    cmd = ["curl", "-s", "--max-time", "30", "-w", "\n%{http_code}",
           "-H", f"Authorization: token {TOKEN}", "-H", "Accept: application/vnd.github+json"]
    tmp = None
    if data is not None:
        fd, tmp = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        cmd += ["-X", "PUT", "--data-binary", "@" + tmp]
    cmd.append(API + path)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if tmp:
        os.unlink(tmp)
    out, _, code = r.stdout.rpartition("\n")
    try:
        return int(code.strip()), json.loads(out or "{}")
    except Exception:
        return 0, {"message": out[:120]}


files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
ok, fail = 0, []
for i, path in enumerate(files, 1):
    with open(path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    _, existing = api(path)  # GET current file to learn its sha (empty on 404)
    payload = {"message": f"Add {path}", "content": content, "branch": "main"}
    if existing.get("sha"):
        payload["sha"] = existing["sha"]
    code, resp = api(path, payload)
    if code in (200, 201):
        ok += 1
        print(f"[{i}/{len(files)}] {path} -> {code}")
    else:
        fail.append(path)
        print(f"[{i}/{len(files)}] {path} -> {code} {str(resp.get('message'))[:80]}")

print(f"\nDONE: {ok}/{len(files)} uploaded, failed: {fail or 'none'}")
sys.exit(1 if fail else 0)
