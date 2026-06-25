"""Quick API smoke test with the real data files."""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def post_json(url, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def post_file(url, filepath, extra_fields=None):
    boundary = "----apiboundary9876"
    parts = []
    if extra_fields:
        for k, v in extra_fields.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
                .encode()
            )
    with open(filepath, "rb") as f:
        data = f.read()
    fname = filepath.split("\\")[-1]
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\nContent-Type: text/csv\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# 1. Create project
res = post_json(f"{BASE}/projects", {"name": "RealDataTest"})
pid = res["project_id"]
print("Project ID:", pid)

# 2. Ingest business (Ahumada)
res = post_file(
    f"{BASE}/business/ingest",
    r"C:\Users\inreynaldo\Downloads\Ahumada20260624.csv",
    {"replace": "true"},
)
print("Business:", res)

# 3. Ingest candidates (Proyecciones)
res = post_file(
    f"{BASE}/projects/{pid}/ingest",
    r"C:\Users\inreynaldo\Downloads\Proyecciones20260624.csv",
)
print("Candidates:", res)

# 4. Get next candidate
res = get(f"{BASE}/projects/{pid}/next")
c = res["candidate"]
print(f"Remaining: {res['remaining']} / Total: {res['total']}")
if c:
    dd = c["display_data"]
    dir_key = next((k for k in dd if "RECC" in k), None)
    score_key = next((k for k in dd if "ROYECC" in k), None)
    print("Address key:", repr(dir_key), "=", repr((dd.get(dir_key) or "")[:60]))
    print("Score key:", repr(score_key), "=", repr(dd.get(score_key)))
    age_bands = {k: v for k, v in dd.items() if ("<" in k or "-" in k) and any(d.isdigit() for d in k)}
    print("Age bands:", age_bands)
    print("Lat:", c["lat"], "Lng:", c["lng"])
