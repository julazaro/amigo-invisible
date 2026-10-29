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

# Conexión TCP a Redis (Railway/cualquier Redis estándar)
r = None
if REDIS_URL:
    import redis as _redis
    try:
        r = _redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print("✓ Redis conectado")
    except Exception as e:
        print(f"✗ Error al conectar Redis: {e}")
        r = None

def default_data():
    return {"drawDone": False, "assignments": {}, "codes": {}, "clues": {}}

def load():
    if r:
        try:
            raw = r.get("amigo-data")
            return json.loads(raw) if raw else default_data()
        except Exception as e:
            print(f"Error leyendo Redis: {e}")
            return default_data()
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_data()

def save(data):
    if r:
        try:
            r.set("amigo-data", json.dumps(data))
        except Exception as e:
            print(f"Error guardando en Redis: {e}")
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
    senderName: str
    senderCode: str
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

# Verifica nombre + código y devuelve a quién le tocó (sin efectos secundarios)
@app.get("/api/verify/{name}")
def verify(name: str, code: str):
    if name not in PARTICIPANTS:
        return {"error": "invalid_name"}
    if not code.isdigit() or len(code) != 4:
        return {"error": "invalid_code_format"}
    d = load()
    if not d["drawDone"]:
        return {"error": "no_draw"}
    if name not in d["codes"] or d["codes"][name] != code:
        return {"error": "wrong_code"}
    return {"ok": True, "assignment": d["assignments"][name]}

# Enviar pista: el remitente se identifica y la pista va a su amigo automáticamente
@app.post("/api/clue")
def clue(req: ClueReq):
    if req.senderName not in PARTICIPANTS:
        return {"error": "invalid_name"}
    if not req.senderCode.isdigit() or len(req.senderCode) != 4:
        return {"error": "invalid_code_format"}
    if len(req.text.strip()) < 2:
        return {"error": "too_short"}
    d = load()
    if not d["drawDone"]:
        return {"error": "no_draw"}
    if req.senderName not in d["codes"] or d["codes"][req.senderName] != req.senderCode:
        return {"error": "wrong_code"}
    recipient = d["assignments"][req.senderName]
    ts = datetime.now().strftime("%d/%m %H:%M")
    if recipient not in d["clues"]:
        d["clues"][recipient] = []
    d["clues"][recipient].append({"text": req.text.strip()[:500], "ts": ts})
    save(d)
    return {"ok": True, "recipient": recipient}

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
