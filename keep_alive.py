
# keep_alive.py — minute pinger (24/7)
import threading, time, requests, os

def _ping(url):
    try:
        requests.head(url, timeout=8)
        return True
    except Exception:
        try:
            requests.get(url, timeout=8)
            return True
        except Exception:
            return False

def start_keep_alive(url: str = "", interval: int = 60):
    def _loop():
        target = url or os.getenv("PUBLIC_URL") or f"http://127.0.0.1:{os.getenv('PORT','10000')}"
        while True:
            ok = _ping(target)
            print("🟢 Keep-alive ping" if ok else "🔴 Keep-alive failed", target)
            time.sleep(interval)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[keep-alive] started every {interval}s -> {url or os.getenv('PUBLIC_URL') or 'local'}")
    return t
