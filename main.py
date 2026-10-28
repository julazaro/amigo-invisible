from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
import json, os, random
from pathlib import Path

app = FastAPI()

ADMIN_CODE   = os.getenv("ADMIN_CODE", "sorteo2026")
REDIS_URL    = os.getenv("REDIS_URL")
DATA_FILE    = Path(__file__).parent / "data.json"
PARTICIPANTS = ["Agus","Cin","Darka","Eri","Gabi","Juli","Kari","Lali","Maru","Tati","Vikz"]

# Redis opcional — si hay REDIS_URL lo usa, si no guarda en data.json
r = None
if REDIS_URL:
    import redis as _redis
    r = _redis.from_url(REDIS_URL, decode_responses=True)

def default_data():
    return {"drawDone": False, "assignments": {}, "codes": {}, "clues": {}}

def load():
    if r:
        raw = r.get("amigo-data")
        return json.loads(raw) if raw else default_data()
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_data()

def save(data):
    if r:
        r.set("amigo-data", json.dumps(data))
        return
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def derange(arr):
    a = arr[:]
    for _ in range(300):
        random.shuffle(a)
        if all(a[i] != arr[i] for i in range(len(arr))):
            return a
        a = arr[:]
    return arr[1:] + arr[:1]

# ── Modelos ───────────────────────────────────────────────────────────────────

class DrawReq(BaseModel):
    adminCode: str

class ClueReq(BaseModel):
    recipient: str
    text: str

class SobreReq(BaseModel):
    name: str
    code: str

class AdminReq(BaseModel):
    adminCode: str

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    d = load()
    return {"drawDone": d["drawDone"], "participants": PARTICIPANTS}

@app.post("/api/draw")
def draw(req: DrawReq):
    if req.adminCode != ADMIN_CODE:
        return {"error": "wrong_code"}
    d = load()
    if d["drawDone"]:
        return {"error": "already_done"}
    shuffled = derange(PARTICIPANTS)
    d["assignments"] = {n: shuffled[i] for i, n in enumerate(PARTICIPANTS)}
    d["drawDone"] = True
    save(d)
    return {"ok": True}

@app.post("/api/clue")
def clue(req: ClueReq):
    if not req.recipient or not req.text:
        return {"error": "missing_fields"}
    if req.recipient not in PARTICIPANTS:
        return {"error": "invalid_recipient"}
    if len(req.text.strip()) < 2:
        return {"error": "too_short"}
    d = load()
    ts = datetime.now().strftime("%d/%m %H:%M")
    if req.recipient not in d["clues"]:
        d["clues"][req.recipient] = []
    d["clues"][req.recipient].append({"text": req.text.strip()[:500], "ts": ts})
    save(d)
    return {"ok": True}

@app.post("/api/sobre")
def sobre(req: SobreReq):
    if not req.name or not req.code:
        return {"error": "missing_fields"}
    if req.name not in PARTICIPANTS:
        return {"error": "invalid_name"}
    if not req.code.isdigit() or len(req.code) != 4:
        return {"error": "invalid_code_format"}
    d = load()
    if not d["drawDone"]:
        return {"error": "no_draw"}
    if req.name not in d["codes"]:
        d["codes"][req.name] = req.code
        save(d)
        return {"ok": True, "isFirst": True, "assignment": d["assignments"][req.name]}
    if d["codes"][req.name] != req.code:
        return {"error": "wrong_code"}
    return {"ok": True, "isFirst": False, "assignment": d["assignments"][req.name]}

@app.get("/api/clues/{name}")
def get_clues(name: str, code: str):
    if name not in PARTICIPANTS:
        return {"error": "invalid_name"}
    d = load()
    if not d["drawDone"]:
        return {"error": "no_draw"}
    if name not in d["codes"] or d["codes"][name] != code:
        return {"error": "wrong_code"}
    return {"ok": True, "clues": d["clues"].get(name, [])}

@app.post("/api/admin/summary")
def admin_summary(req: AdminReq):
    if req.adminCode != ADMIN_CODE:
        return {"error": "wrong_code"}
    d = load()
    summary = [
        {"name": n, "clueCount": len(d["clues"].get(n, [])), "hasCode": n in d["codes"]}
        for n in PARTICIPANTS
    ]
    return {"ok": True, "drawDone": d["drawDone"], "summary": summary}

# Sirve el frontend (va al final, después de todas las rutas /api/)
app.mount("/", StaticFiles(directory="public", html=True), name="static")
