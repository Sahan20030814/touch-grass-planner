#!/usr/bin/env python3
"""Touch Grass Planner v2: local-first outdoor companion. Python stdlib only.
Open pieces: Gemma (via Ollama) writes plans, BirdNET identifies bird calls, Open-Meteo gives weather."""
import csv, json, math, os, subprocess, sys, tempfile, urllib.request
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", ROOT)); DATA.mkdir(exist_ok=True)
JOURNAL, LIFE = DATA / "journal.json", DATA / "birds.json"
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("TG_MODEL", "gemma3:4b")

# Frost climates: (name, anchor, from_week, to_week, how); weeks from last spring / first fall frost.
FROST = [
    ("Peas", "spring", -6, -2, "Direct sow"), ("Spinach", "spring", -6, -2, "Direct sow"),
    ("Lettuce", "spring", -4, 4, "Sow"), ("Radish", "spring", -4, 6, "Sow"),
    ("Potatoes", "spring", -4, 0, "Plant seed potatoes"), ("Carrots", "spring", -3, 4, "Direct sow"),
    ("Tomatoes", "spring", 1, 3, "Transplant"), ("Beans", "spring", 1, 8, "Direct sow"),
    ("Squash", "spring", 1, 6, "Direct sow"), ("Basil", "spring", 2, 6, "Transplant"),
    ("Garlic", "fall", 1, 6, "Plant cloves"), ("Spinach (fall)", "fall", -8, -3, "Direct sow"),
    ("Kale", "fall", -12, -6, "Transplant"), ("Radish (fall)", "fall", -6, -2, "Sow"),
    ("Rye cover crop", "fall", -4, 3, "Broadcast"), ("Tulips and daffodils", "fall", 2, 8, "Plant bulbs"),
]
# Tropical (Sri Lanka, hill country/intermediate zone): (name, sowing months, how). General guide only;
# confirm with your local Department of Agriculture office.
TROPICAL = [
    ("Okra", (10, 11, 12, 2, 3), "Direct sow"), ("Brinjal", (10, 11, 4, 5), "Transplant"),
    ("Long beans", (10, 11, 12, 3, 4, 5), "Direct sow"), ("Chili", (10, 11, 3, 4), "Transplant"),
    ("Tomato", (10, 11, 12, 1), "Transplant"), ("Carrot", (10, 11, 12, 1, 3, 4), "Direct sow"),
    ("Cabbage", (9, 10, 11, 12), "Transplant"), ("Pumpkin", (10, 11), "Direct sow"),
    ("Beetroot", (10, 11, 12, 3, 4), "Direct sow"), ("Gotukola", tuple(range(1, 13)), "Divide and replant"),
    ("Kankun", tuple(range(1, 13)), "Cuttings"), ("Maize", (10, 11, 4, 5), "Direct sow"),
]
WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 80: "showers", 81: "showers", 82: "heavy showers", 95: "thunderstorm",
       96: "thunderstorm", 99: "thunderstorm"}
SYSTEM = ("You are a friendly outdoor coach. Reply in plain text, no markdown, under 110 words. "
          "Format: a short title line, then exactly 3 short steps starting with '-', then one line "
          "starting 'Leave behind:' naming what to leave at home. Be specific and practical.")


def garden(a):
    today = date.today()
    if a.get("climate") == "tropical":
        m, nm = today.month, today.month % 12 + 1
        now = [{"name": n, "how": h} for n, ms, h in TROPICAL if m in ms]
        soon = [{"name": n, "how": h} for n, ms, h in TROPICAL if nm in ms and m not in ms]
        s = "Maha season (north-east monsoon)" if m in (10, 11, 12, 1, 2) else "Yala season (south-west monsoon)"
        return {"now": now, "soon": soon, "season": s}
    yr = lambda s: datetime.strptime(s, "%Y-%m-%d").date().replace(year=today.year)
    lf, ff = yr(a["last"]), yr(a["first"])
    out = {"now": [], "soon": [], "days_to_first_frost": (ff - today).days}
    for name, anchor, x, y, how in FROST:
        off = (today - (lf if anchor == "spring" else ff)).days / 7
        item = {"name": name, "how": how}
        if x <= off <= y: out["now"].append(item)
        elif 0 < x - off <= 2: out["soon"].append(item)
    return out


def weather(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,weather_code,wind_speed_10m&daily=sunset&timezone=auto&forecast_days=1")
    try:
        with urllib.request.urlopen(url, timeout=6) as r: j = json.load(r)
        c = j["current"]
        return {"text": f"{c['temperature_2m']:.0f}°C, {WMO.get(c['weather_code'], 'mixed')}, "
                        f"wind {c['wind_speed_10m']:.0f} km/h, sunset {j['daily']['sunset'][0][11:16]}"}
    except Exception:
        return {"error": "No internet for live weather. Type conditions by hand."}


def birds(wav, lat, lon):
    try: import birdnet_analyzer  # noqa: F401
    except ImportError: return {"error": "BirdNET not installed. Run: pip install birdnet-analyzer"}
    with tempfile.TemporaryDirectory() as t:
        f, out = Path(t) / "clip.wav", Path(t) / "out"
        f.write_bytes(wav)
        cmd = [sys.executable, "-m", "birdnet_analyzer.analyze", str(f), "-o", str(out), "--min_conf", "0.2", "--rtype", "csv"]
        if lat and lon:
            wk = min(48, max(1, round(date.today().isocalendar()[1] * 48 / 52)))
            cmd += ["--lat", lat, "--lon", lon, "--week", str(wk)]
        try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired: return {"error": "Identification timed out. Try a shorter clip."}
        best = {}
        for c in out.glob("*.csv"):
            for row in csv.DictReader(c.open(encoding="utf-8")):
                k, cf = row["Common name"], float(row["Confidence"])
                if cf > best.get(k, (0, ""))[0]: best[k] = (cf, row["Scientific name"])
        if not best and r.returncode: return {"error": "BirdNET failed: " + r.stderr[-250:]}
    top = [{"name": k, "sci": v[1], "conf": v[0]} for k, v in sorted(best.items(), key=lambda x: -x[1][0])[:5]]
    life = set(json.loads(LIFE.read_text())) if LIFE.exists() else set()
    life |= {b["name"] for b in top if b["conf"] >= 0.5}
    LIFE.write_text(json.dumps(sorted(life)))
    return {"birds": top, "lifelist": len(life)}


def ask_llm(prompt):
    body = json.dumps({"model": MODEL, "stream": False, "options": {"temperature": 0.7, "num_predict": 300},
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r: return json.load(r)["message"]["content"].strip()


def fallback(d):
    return (f"{d['minutes']} minute {d['activity']} outside\n- Pick a direction you have not gone before.\n"
            "- Keep your phone in your pocket and notice three things changing this season.\n"
            "- Turn back when half your time is used.\nLeave behind: headphones and notifications.")


def read_journal(): return json.loads(JOURNAL.read_text()) if JOURNAL.exists() else []
def qargs(q): return dict(x.split("=", 1) for x in q.split("&") if "=" in x)


class H(BaseHTTPRequestHandler):
    def send(self, obj, code=200, ctype="application/json"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        p, _, q = self.path.partition("?"); a = qargs(q)
        if p == "/": return self.send((ROOT / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
        if p == "/api/status":
            try:
                with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2) as r: names = [m["name"] for m in json.load(r)["models"]]
                return self.send({"ollama": True, "model": MODEL, "ready": any(n.startswith(MODEL.split(":")[0]) for n in names)})
            except Exception: return self.send({"ollama": False, "model": MODEL, "ready": False})
        if p == "/api/garden":
            try: return self.send(garden(a))
            except Exception: return self.send({"error": "Enter both frost dates."}, 400)
        if p == "/api/weather": return self.send(weather(a.get("lat", ""), a.get("lon", "")))
        if p == "/api/journal": return self.send(read_journal())
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 25_000_000))
        p, _, q = self.path.partition("?")
        if p == "/api/birds": return self.send(birds(raw, *(qargs(q).get(k, "") for k in ("lat", "lon"))))
        d = json.loads(raw or b"{}")
        if p == "/api/plan":
            prompt = (f"Activity: {d.get('activity')}. Time available: {d.get('minutes')} minutes. Month: {date.today():%B}. "
                      f"Conditions: {d.get('weather') or 'unknown'}. Garden jobs due: {', '.join(d.get('garden') or []) or 'none'}. Write the plan.")
            try: return self.send({"plan": ask_llm(prompt), "source": MODEL})
            except Exception: return self.send({"plan": fallback(d), "source": "offline template (model not running)"})
        if p == "/api/journal":
            j = read_journal()
            j.append({"date": date.today().isoformat(), "minutes": int(d.get("minutes", 0)),
                      "activity": d.get("activity", ""), "note": d.get("note", "")[:200]})
            JOURNAL.write_text(json.dumps(j, indent=1)); return self.send(j)
        self.send({"error": "not found"}, 404)

    def log_message(self, *a): pass


if __name__ == "__main__":
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", 8000))
    print(f"Touch Grass Planner on http://localhost:{port}  (model: {MODEL})")
    ThreadingHTTPServer((host, port), H).serve_forever()
