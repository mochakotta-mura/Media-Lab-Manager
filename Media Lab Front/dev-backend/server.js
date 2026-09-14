'use strict';

// DEVELOPMENT ONLY. This file intentionally owns a separate SQLite database.
const http = require('node:http');
const { DatabaseSync } = require('node:sqlite');
const path = require('node:path');
const fs = require('node:fs');

const port = Number(process.env.MLM_DEV_PORT || 3000);
const dataDir = path.join(__dirname, 'data');
fs.mkdirSync(dataDir, { recursive: true });
const db = new DatabaseSync(process.env.MLM_DEV_DB || path.join(dataDir, 'media-lab-dev.sqlite'));
db.exec(`
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, krea_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL, email TEXT UNIQUE, department TEXT DEFAULT '', role TEXT DEFAULT 'lendee', notification_preferences TEXT DEFAULT '{}', banned INTEGER DEFAULT 0, ban_reason TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS equipment (id INTEGER PRIMARY KEY, asset_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT DEFAULT '', serial_number TEXT UNIQUE, status TEXT DEFAULT 'available' CHECK(status IN ('available','requested','pickup_pending','picked_up','overdue','damaged','maintenance','retired','lost')), location TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS equipment_tags (equipment_id INTEGER REFERENCES equipment(id) ON DELETE CASCADE, tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE, PRIMARY KEY(equipment_id, tag_id));
CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, requester_id INTEGER NOT NULL REFERENCES users(id), purpose TEXT DEFAULT '', academic_priority INTEGER DEFAULT 0, status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','cancelled','pickup_pending','picked_up','returned','overdue','completed')), rejection_reason TEXT DEFAULT '', approval_notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS request_items (id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE, equipment_id INTEGER NOT NULL REFERENCES equipment(id), status TEXT DEFAULT 'requested', UNIQUE(request_id, equipment_id));
CREATE TABLE IF NOT EXISTS time_windows (id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE, kind TEXT NOT NULL CHECK(kind IN ('pickup','return','extension')), starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, status TEXT DEFAULT 'requested', notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS returns (id INTEGER PRIMARY KEY, request_item_id INTEGER NOT NULL UNIQUE REFERENCES request_items(id), picked_up_at TEXT, returned_at TEXT, returned_flag INTEGER DEFAULT 0, condition TEXT DEFAULT '', damage_flag INTEGER DEFAULT 0, notes TEXT DEFAULT '', no_show INTEGER DEFAULT 0, overdue_warning_count INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS damage_reports (id INTEGER PRIMARY KEY, request_item_id INTEGER NOT NULL REFERENCES request_items(id), reported_by INTEGER REFERENCES users(id), description TEXT NOT NULL, severity TEXT DEFAULT 'unknown', resolved INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ban_history (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL, reason TEXT DEFAULT '', actor_id INTEGER REFERENCES users(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, action TEXT NOT NULL, details TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS outbox_events (id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, aggregate_type TEXT NOT NULL, aggregate_id INTEGER NOT NULL, payload TEXT DEFAULT '{}', published_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_equipment_status ON equipment(status); CREATE INDEX IF NOT EXISTS idx_request_status ON requests(status); CREATE INDEX IF NOT EXISTS idx_windows_time ON time_windows(kind, starts_at, ends_at);
`);

const now = () => new Date().toISOString();
const json = value => JSON.stringify(value || {});
const one = (sql, ...params) => db.prepare(sql).get(...params);
const many = (sql, ...params) => db.prepare(sql).all(...params);
const run = (sql, ...params) => db.prepare(sql).run(...params);
function audit(actor, type, id, action, details = {}) { run('INSERT INTO audit_log(actor_id,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)', actor || null, type, id, action, json(details)); }
function emit(type, aggregateType, id, payload = {}) { run('INSERT INTO outbox_events(event_type,aggregate_type,aggregate_id,payload) VALUES (?,?,?,?)', type, aggregateType, id, json(payload)); }

function seed() {
  if (one('SELECT COUNT(*) AS count FROM users').count) return;
  run('INSERT INTO users(krea_id,name,email,department,role) VALUES (?,?,?,?,?)', 'dev-student', 'Alex Rivera', 'alex@example.edu', 'Communication & Film', 'lendee');
  run('INSERT INTO users(krea_id,name,email,department,role) VALUES (?,?,?,?,?)', 'dev-admin', 'Professor Marcus', 'marcus@example.edu', 'Communication & Film', 'admin');
  const gear = [
    ['UML-CAM-01','Sony A6400 Camera Body','Mirrorless camera body','SN-A6400-01','available','Room 204'],
    ['UML-CAM-02','Sony ZV-E10 Camera Body','Compact video camera','SN-ZVE10-02','available','Room 204'],
    ['UML-LEN-01','Sony 35mm f/1.8','Prime lens','SN-3518-01','available','Room 204'],
    ['UML-AUD-01','RØDE Shotgun Microphone','Directional microphone kit','SN-RODE-01','available','Room 204'],
    ['UML-LGT-01','Godox 1000W Light','Studio light','SN-GODOX-01','maintenance','Room 205'],
    ['UML-GRP-01','Light Stand','Adjustable stand','SN-STAND-01','available','Room 205']
  ];
  gear.forEach(item => run('INSERT INTO equipment(asset_code,name,description,serial_number,status,location) VALUES (?,?,?,?,?,?)', ...item));
  const student = one('SELECT id FROM users WHERE krea_id=?', 'dev-student').id;
  const cam = one('SELECT id FROM equipment WHERE asset_code=?', 'UML-CAM-01').id;
  const mic = one('SELECT id FROM equipment WHERE asset_code=?', 'UML-AUD-01').id;
  const r = run('INSERT INTO requests(requester_id,purpose,academic_priority,status) VALUES (?,?,?,?)', student, 'Development seed request', 1, 'pending');
  run('INSERT INTO request_items(request_id,equipment_id) VALUES (?,?)', r.lastInsertRowid, cam); run('INSERT INTO request_items(request_id,equipment_id) VALUES (?,?)', r.lastInsertRowid, mic);
  run('INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)', r.lastInsertRowid, 'pickup', '2026-09-20T14:00:00.000Z', '2026-09-20T15:00:00.000Z');
  run('INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)', r.lastInsertRowid, 'return', '2026-09-23T16:00:00.000Z', '2026-09-23T17:00:00.000Z');
  audit(student, 'request', Number(r.lastInsertRowid), 'created', { seed: true }); emit('request.created', 'request', Number(r.lastInsertRowid), { seed: true });
}
seed();

function requestView(id) {
  const request = one('SELECT r.*,u.krea_id,u.name AS requester_name,u.email AS requester_email FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.id=?', Number(id));
  if (!request) return null;
  request.items = many('SELECT ri.*,e.asset_code,e.name,e.description,e.status AS equipment_status,e.serial_number FROM request_items ri JOIN equipment e ON e.id=ri.equipment_id WHERE ri.request_id=?', Number(id));
  request.windows = many('SELECT * FROM time_windows WHERE request_id=? ORDER BY starts_at', Number(id));
  return request;
}
function equipment(filters = {}) {
  const clauses = [], params = [];
  if (filters.status) { clauses.push('status=?'); params.push(filters.status); }
  if (filters.q) { clauses.push('(name LIKE ? OR asset_code LIKE ? OR serial_number LIKE ? OR description LIKE ?)'); params.push(...Array(4).fill('%' + filters.q + '%')); }
  const limit = Math.min(Math.max(Number(filters.limit) || 100, 1), 1000), offset = Math.max(Number(filters.offset) || 0, 0);
  return many(`SELECT * FROM equipment ${clauses.length ? 'WHERE ' + clauses.join(' AND ') : ''} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?`, ...params, limit, offset);
}
function checkAvailability(ids, startsAt, endsAt) {
  if (!ids.length || !startsAt || !endsAt) return [];
  const marks = ids.map(() => '?').join(',');
  return many(`SELECT DISTINCT ri.equipment_id FROM request_items ri JOIN requests r ON r.id=ri.request_id JOIN time_windows w ON w.request_id=r.id WHERE ri.equipment_id IN (${marks}) AND r.status IN ('pending','approved','pickup_pending','picked_up','overdue') AND w.status IN ('requested','approved') AND w.starts_at < ? AND w.ends_at > ?`, ...ids, endsAt, startsAt).map(x => x.equipment_id);
}
function createRequest(body) {
  const ids = [...new Set((body.equipmentIds || []).map(Number))].filter(Boolean); const user = one('SELECT * FROM users WHERE id=?', Number(body.requesterId));
  if (!user) throw new Error('user not found'); if (user.banned) throw new Error('user is banned'); if (!ids.length) throw new Error('equipmentIds are required');
  const missing = ids.filter(equipmentId => !one('SELECT id FROM equipment WHERE id=?', equipmentId)); if (missing.length) throw new Error('equipment not found: ' + missing.join(','));
  const conflicts = checkAvailability(ids, body.pickupStartsAt, body.returnEndsAt); if (conflicts.length) throw new Error('equipment unavailable: ' + conflicts.join(','));
  const result = run('INSERT INTO requests(requester_id,purpose,academic_priority) VALUES (?,?,?)', user.id, body.purpose || '', Number(body.academicPriority) || 0); const id = Number(result.lastInsertRowid);
  ids.forEach(equipmentId => { run('INSERT INTO request_items(request_id,equipment_id) VALUES (?,?)', id, equipmentId); run("UPDATE equipment SET status='requested',updated_at=? WHERE id=?", now(), equipmentId); });
  if (body.pickupStartsAt && body.pickupEndsAt) run('INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)', id, 'pickup', body.pickupStartsAt, body.pickupEndsAt);
  if (body.returnStartsAt && body.returnEndsAt) run('INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)', id, 'return', body.returnStartsAt, body.returnEndsAt);
  audit(user.id, 'request', id, 'created', { equipmentIds: ids }); emit('request.created', 'request', id, { equipmentIds: ids }); return requestView(id);
}
function setStatus(id, status, actorId, details = {}) {
  const request = one('SELECT * FROM requests WHERE id=?', Number(id)); if (!request) throw new Error('request not found');
  run('UPDATE requests SET status=?,rejection_reason=?,approval_notes=?,updated_at=? WHERE id=?', status, details.reason || request.rejection_reason, details.notes || request.approval_notes, now(), id); run('UPDATE request_items SET status=? WHERE request_id=?', status, id);
  if (status === 'approved') run("UPDATE equipment SET status='pickup_pending',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", now(), id);
  if (status === 'rejected' || status === 'cancelled') run("UPDATE equipment SET status='available',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", now(), id);
  audit(actorId, 'request', Number(id), status, details); emit('request.' + status, 'request', Number(id), details); return requestView(id);
}

async function body(req) { let text = ''; for await (const chunk of req) text += chunk; return text ? JSON.parse(text) : {}; }
function send(res, status, data) { const text = JSON.stringify(data); res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Headers': 'Content-Type' }); res.end(text); }
function routeError(res, error) { send(res, /not found/i.test(error.message) ? 404 : 400, { error: error.message }); }

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {});
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`); const parts = url.pathname.split('/').filter(Boolean); if (parts[0] !== 'api') return send(res, 404, { error: 'Development API only' });
  try {
    const data = ['POST','PUT','PATCH'].includes(req.method) ? await body(req) : {};
    if (req.method === 'GET' && parts[1] === 'equipment' && parts[2] === 'stats') return send(res, 200, many('SELECT status,COUNT(*) AS count FROM equipment GROUP BY status ORDER BY status'));
    if (req.method === 'GET' && parts[1] === 'equipment') return send(res, 200, equipment(Object.fromEntries(url.searchParams)));
    if (req.method === 'POST' && parts[1] === 'users') { if (!data.kreaId || !data.name) throw new Error('kreaId and name are required'); const existing = one('SELECT * FROM users WHERE krea_id=?', data.kreaId); const user = existing || (run('INSERT INTO users(krea_id,name,email,department,role) VALUES (?,?,?,?,?)', data.kreaId, data.name, data.email || null, data.department || '', data.role || 'lendee'), one('SELECT * FROM users WHERE krea_id=?', data.kreaId)); return send(res, 201, user); }
    if (req.method === 'POST' && parts[1] === 'requests' && parts.length === 2) return send(res, 201, createRequest(data));
    if (req.method === 'GET' && parts[1] === 'requests') { const clauses = [], params = []; if (url.searchParams.get('requesterId')) { clauses.push('r.requester_id=?'); params.push(Number(url.searchParams.get('requesterId'))); } if (url.searchParams.get('status')) { clauses.push('r.status=?'); params.push(url.searchParams.get('status')); } const rows = many(`SELECT r.*,u.name AS requester_name,u.email AS requester_email FROM requests r JOIN users u ON u.id=r.requester_id ${clauses.length ? 'WHERE ' + clauses.join(' AND ') : ''} ORDER BY r.created_at DESC`, ...params).map(x => requestView(x.id)); return send(res, 200, rows); }
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'approve') return send(res, 200, setStatus(parts[2], 'approved', data.actorId, { notes: data.notes || '' }));
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'reject') return send(res, 200, setStatus(parts[2], 'rejected', data.actorId, { reason: data.reason || '' }));
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'cancel') return send(res, 200, setStatus(parts[2], 'cancelled', data.actorId));
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'windows') { run('INSERT INTO time_windows(request_id,kind,starts_at,ends_at,status,notes) VALUES (?,?,?,?,?,?)', data.requestId, data.kind || 'extension', data.startsAt, data.endsAt, data.status || 'requested', data.notes || ''); audit(data.actorId, 'request', data.requestId, 'window_scheduled', data); emit('window.updated', 'request', data.requestId, data); return send(res, 201, one('SELECT * FROM time_windows WHERE id=last_insert_rowid()')); }
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'extensions') { data.kind = 'extension'; data.status = 'requested'; run('INSERT INTO time_windows(request_id,kind,starts_at,ends_at,status,notes) VALUES (?,?,?,?,?,?)', parts[2], 'extension', data.startsAt, data.endsAt, 'requested', data.notes || ''); audit(data.actorId, 'request', Number(parts[2]), 'extension_requested', data); emit('window.updated', 'request', Number(parts[2]), data); return send(res, 201, requestView(parts[2])); }
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'pickup') { const ids = data.requestItemIds || many('SELECT id FROM request_items WHERE request_id=?', parts[2]).map(x => x.id); ids.forEach(id => { run('INSERT INTO returns(request_item_id,picked_up_at) VALUES (?,?) ON CONFLICT(request_item_id) DO UPDATE SET picked_up_at=excluded.picked_up_at', id, data.pickedUpAt || now()); run("UPDATE request_items SET status='picked_up' WHERE id=?", id); }); run("UPDATE requests SET status='picked_up',updated_at=? WHERE id=?", now(), parts[2]); run("UPDATE equipment SET status='picked_up',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", now(), parts[2]); audit(data.actorId, 'request', Number(parts[2]), 'pickup_confirmed', data); emit('pickup.confirmed', 'request', Number(parts[2]), data); return send(res, 200, requestView(parts[2])); }
    if (req.method === 'POST' && parts[1] === 'requests' && parts[3] === 'return') { const ids = data.requestItemIds || many('SELECT id FROM request_items WHERE request_id=?', parts[2]).map(x => x.id); ids.forEach(id => { run('INSERT INTO returns(request_item_id,returned_at,returned_flag,condition,damage_flag,notes) VALUES (?,?,1,?,?,?) ON CONFLICT(request_item_id) DO UPDATE SET returned_at=excluded.returned_at,returned_flag=1,condition=excluded.condition,damage_flag=excluded.damage_flag,notes=excluded.notes', id, data.returnedAt || now(), data.condition || '', data.damageFlag ? 1 : 0, data.notes || ''); run('UPDATE request_items SET status=? WHERE id=?', data.damageFlag ? 'damaged' : 'returned', id); }); run("UPDATE requests SET status='returned',updated_at=? WHERE id=?", now(), parts[2]); run("UPDATE equipment SET status=?,updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", data.damageFlag ? 'damaged' : 'available', now(), parts[2]); audit(data.actorId, 'request', Number(parts[2]), 'return_recorded', data); emit('return.recorded', 'request', Number(parts[2]), data); return send(res, 200, requestView(parts[2])); }
    if (req.method === 'POST' && parts[1] === 'request-items' && parts[3] === 'damage') { const result = run('INSERT INTO damage_reports(request_item_id,reported_by,description,severity) VALUES (?,?,?,?)', parts[2], data.reportedBy || null, data.description || 'Development damage report', data.severity || 'unknown'); run("UPDATE request_items SET status='damaged' WHERE id=?", parts[2]); audit(data.reportedBy, 'request_item', Number(parts[2]), 'damage_reported', data); emit('damage.reported', 'request_item', Number(parts[2]), data); return send(res, 201, one('SELECT * FROM damage_reports WHERE id=?', result.lastInsertRowid)); }
    if (req.method === 'GET' && parts[1] === 'dashboard') return send(res, 200, { pendingRequests: many("SELECT r.*,u.name AS requester_name FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.status='pending' ORDER BY r.academic_priority DESC,r.created_at"), windows: many('SELECT w.*,r.status,u.name AS requester_name FROM time_windows w JOIN requests r ON r.id=w.request_id JOIN users u ON u.id=r.requester_id ORDER BY w.starts_at'), equipment: many('SELECT * FROM equipment ORDER BY name COLLATE NOCASE') });
    if (req.method === 'GET' && parts[1] === 'audit') return send(res, 200, many('SELECT * FROM audit_log WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC', parts[2], Number(parts[3])));
    if (req.method === 'GET' && parts[1] === 'outbox') return send(res, 200, many('SELECT * FROM outbox_events WHERE published_at IS NULL ORDER BY id LIMIT 100'));
    return send(res, 404, { error: 'Endpoint not found' });
  } catch (error) { routeError(res, error); }
});
server.listen(port, '127.0.0.1', () => console.log(`Media Lab development API listening at http://localhost:${port}/api`));
process.on('SIGINT', () => { db.close(); server.close(() => process.exit(0)); });
