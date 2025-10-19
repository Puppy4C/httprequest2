import urllib.parse
import urllib.request

q = "测试"
base = "http://107.174.71.236/api/search"
url = base + "?" + urllib.parse.urlencode({"q": q}, encoding="utf-8")

req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3"})
with urllib.request.urlopen(req) as resp:
    status = resp.getcode()
    body = resp.read()
    try:
        text = body.decode("utf-8")
    except Exception:
        text = body.decode("latin1", errors="replace")

print(f"HTTP {status}\n")
print(text)