const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const ADMIN_CODE  = process.env.ADMIN_CODE || 'sorteo2026';
const REDIS_URL   = process.env.UPSTASH_REDIS_REST_URL;
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN;
const DATA_FILE   = path.join(__dirname, 'data.json');
const PARTICIPANTS = ['Agus','Cin','Darka','Eri','Gabi','Juli','Kari','Lali','Maru','Tati','Vikz'];

function defaultData() {
  return { drawDone: false, assignments: {}, codes: {}, clues: {} };
}

// Si hay credenciales de Upstash, usa Redis; si no, usa archivo local (dev)
async function load() {
  if (REDIS_URL) {
    try {
      const r = await fetch(`${REDIS_URL}/get/amigo-data`, {
        headers: { Authorization: `Bearer ${REDIS_TOKEN}` }
      });
      const j = await r.json();
      return j.result ? JSON.parse(j.result) : defaultData();
    } catch { return defaultData(); }
  }
  try { return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8')); }
  catch { return defaultData(); }
}

async function save(data) {
  if (REDIS_URL) {
    await fetch(`${REDIS_URL}/set/amigo-data`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${REDIS_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(JSON.stringify(data))
    });
    return;
  }
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

function derange(arr) {
  const a = [...arr];
  for (let t = 0; t < 300; t++) {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    if (a.every((v, i) => v !== arr[i])) return a;
    a.splice(0, a.length, ...arr);
  }
  return [...arr.slice(1), arr[0]];
}

app.get('/api/status', async (req, res) => {
  const d = await load();
  res.json({ drawDone: d.drawDone, participants: PARTICIPANTS });
});

app.post('/api/draw', async (req, res) => {
  const { adminCode } = req.body || {};
  if (adminCode !== ADMIN_CODE) return res.json({ error: 'wrong_code' });
  const d = await load();
  if (d.drawDone) return res.json({ error: 'already_done' });
  const assigned = derange(PARTICIPANTS);
  PARTICIPANTS.forEach((n, i) => { d.assignments[n] = assigned[i]; });
  d.drawDone = true;
  await save(d);
  res.json({ ok: true });
});

app.post('/api/clue', async (req, res) => {
  const { recipient, text } = req.body || {};
  if (!recipient || !text) return res.json({ error: 'missing_fields' });
  if (!PARTICIPANTS.includes(recipient)) return res.json({ error: 'invalid_recipient' });
  if (text.trim().length < 2) return res.json({ error: 'too_short' });
  const d = await load();
  if (!d.clues[recipient]) d.clues[recipient] = [];
  d.clues[recipient].push({
    text: text.trim().slice(0, 500),
    ts: new Date().toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  });
  await save(d);
  res.json({ ok: true });
});

app.post('/api/sobre', async (req, res) => {
  const { name, code } = req.body || {};
  if (!name || !code) return res.json({ error: 'missing_fields' });
  if (!PARTICIPANTS.includes(name)) return res.json({ error: 'invalid_name' });
  if (!/^\d{4}$/.test(code)) return res.json({ error: 'invalid_code_format' });
  const d = await load();
  if (!d.drawDone) return res.json({ error: 'no_draw' });
  if (!d.codes[name]) {
    d.codes[name] = code;
    await save(d);
    return res.json({ ok: true, isFirst: true, assignment: d.assignments[name] });
  }
  if (d.codes[name] !== code) return res.json({ error: 'wrong_code' });
  res.json({ ok: true, isFirst: false, assignment: d.assignments[name] });
});

app.get('/api/clues/:name', async (req, res) => {
  const { name } = req.params;
  const { code } = req.query;
  if (!PARTICIPANTS.includes(name)) return res.json({ error: 'invalid_name' });
  const d = await load();
  if (!d.drawDone) return res.json({ error: 'no_draw' });
  if (!d.codes[name] || d.codes[name] !== code) return res.json({ error: 'wrong_code' });
  res.json({ ok: true, clues: d.clues[name] || [] });
});

app.post('/api/admin/summary', async (req, res) => {
  const { adminCode } = req.body || {};
  if (adminCode !== ADMIN_CODE) return res.json({ error: 'wrong_code' });
  const d = await load();
  const summary = PARTICIPANTS.map(n => ({
    name: n,
    clueCount: (d.clues[n] || []).length,
    hasCode: !!d.codes[n]
  }));
  res.json({ ok: true, drawDone: d.drawDone, summary });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Amigo Invisible en http://localhost:${PORT}`));
