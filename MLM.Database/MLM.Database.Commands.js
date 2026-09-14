'use strict';

const path = require('node:path');
const Database = require('better-sqlite3');

const dbPath = process.env.MEDIA_LAB_DB || path.join(__dirname, 'media-lab.sqlite');
const db = new Database(dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, krea_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  email TEXT UNIQUE, department TEXT DEFAULT '', role TEXT DEFAULT 'lendee',
  notification_preferences TEXT DEFAULT '{}', banned INTEGER DEFAULT 0,
  ban_reason TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP, pin_hash TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS equipment (
  id INTEGER PRIMARY KEY, asset_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  description TEXT DEFAULT '', serial_number TEXT UNIQUE,
  status TEXT DEFAULT 'available' CHECK(status IN
    ('available','requested','pickup_pending','picked_up','overdue','damaged','maintenance','retired','lost')),
  location TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS equipment_tags (
  equipment_id INTEGER REFERENCES equipment(id) ON DELETE CASCADE,
  tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY(equipment_id, tag_id)
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY, requester_id INTEGER NOT NULL REFERENCES users(id),
  purpose TEXT DEFAULT '', academic_priority INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending' CHECK(status IN
    ('pending','approved','rejected','cancelled','pickup_pending','picked_up','returned','overdue','completed')),
  rejection_reason TEXT DEFAULT '', approval_notes TEXT DEFAULT '',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS request_items (
  id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
  equipment_id INTEGER NOT NULL REFERENCES equipment(id), status TEXT DEFAULT 'requested',
  UNIQUE(request_id, equipment_id)
);
CREATE TABLE IF NOT EXISTS time_windows (
  id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('pickup','return','extension')),
  starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, status TEXT DEFAULT 'requested',
  notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS returns (
  id INTEGER PRIMARY KEY, request_item_id INTEGER NOT NULL UNIQUE REFERENCES request_items(id),
  picked_up_at TEXT, returned_at TEXT, returned_flag INTEGER DEFAULT 0,
  condition TEXT DEFAULT '', damage_flag INTEGER DEFAULT 0, notes TEXT DEFAULT '',
  no_show INTEGER DEFAULT 0, overdue_warning_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS damage_reports (
  id INTEGER PRIMARY KEY, request_item_id INTEGER NOT NULL REFERENCES request_items(id),
  reported_by INTEGER REFERENCES users(id), description TEXT NOT NULL,
  severity TEXT DEFAULT 'unknown', resolved INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ban_history (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  action TEXT NOT NULL, reason TEXT DEFAULT '', actor_id INTEGER REFERENCES users(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id),
  entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL, action TEXT NOT NULL,
  details TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS outbox_events (
  id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, aggregate_type TEXT NOT NULL,
  aggregate_id INTEGER NOT NULL, payload TEXT DEFAULT '{}', published_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_equipment_status ON equipment(status);
CREATE INDEX IF NOT EXISTS idx_request_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_windows_time ON time_windows(kind, starts_at, ends_at);
`);

// Existing databases are upgraded only with the one credential field needed by PIN login.
try { db.exec("ALTER TABLE users ADD COLUMN pin_hash TEXT DEFAULT ''"); }
catch (error) { if (!/duplicate column name/i.test(error.message)) throw error; }

const now = () => new Date().toISOString();
const arr = x => Array.isArray(x) ? x : x == null ? [] : [x];
const json = x => JSON.stringify(x || {});
const audit = (actor, type, id, action, details = {}) =>
  db.prepare('INSERT INTO audit_log(actor_id,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)')
    .run(actor || null, type, id, action, json(details));
const emit = (type, aggregateType, id, payload = {}) =>
  db.prepare('INSERT INTO outbox_events(event_type,aggregate_type,aggregate_id,payload) VALUES (?,?,?,?)')
    .run(type, aggregateType, id, json(payload));

function addUser(x = {}) {
  if (!x.kreaId || !x.name) throw new Error('kreaId and name are required');
  const r = db.prepare('INSERT INTO users(krea_id,name,email,department,role,notification_preferences,pin_hash) VALUES (?,?,?,?,?,?,?)')
    .run(x.kreaId, x.name, x.email || null, x.department || '', x.role || 'lendee', json(x.notificationPreferences), x.pinHash || '');
  return db.prepare('SELECT * FROM users WHERE id=?').get(r.lastInsertRowid);
}
function updateUser(id, x = {}) {
  const map = { kreaId:'krea_id', name:'name', email:'email', department:'department', role:'role', banned:'banned', banReason:'ban_reason' };
  const fields = [], params = { id, updatedAt: now() };
  for (const key of Object.keys(map)) if (x[key] !== undefined) { fields.push(map[key] + '=@' + key); params[key] = x[key]; }
  if (fields.length) db.prepare('UPDATE users SET ' + fields.join(',') + ',updated_at=@updatedAt WHERE id=@id').run(params);
  return db.prepare('SELECT * FROM users WHERE id=?').get(id);
}
function banUser(id, reason, actorId) {
  const tx = db.transaction(() => { updateUser(id, { banned:1, banReason:reason || '' }); db.prepare('INSERT INTO ban_history(user_id,action,reason,actor_id) VALUES (?,?,?,?)').run(id, 'banned', reason || '', actorId || null); audit(actorId, 'user', id, 'banned', { reason }); emit('user.banned', 'user', id, { reason }); });
  tx(); return updateUser(id);
}
function unbanUser(id, actorId) {
  const tx = db.transaction(() => { updateUser(id, { banned:0, banReason:'' }); db.prepare('INSERT INTO ban_history(user_id,action,actor_id) VALUES (?,?,?)').run(id, 'unbanned', actorId || null); audit(actorId, 'user', id, 'unbanned'); emit('user.unbanned', 'user', id); });
  tx(); return updateUser(id);
}

function addEquipment(x = {}) {
  if (!x.name) throw new Error('name is required');
  const r = db.prepare('INSERT INTO equipment(asset_code,name,description,serial_number,status,location) VALUES (?,?,?,?,?,?)')
    .run(x.assetCode || 'ASSET-' + Date.now(), x.name, x.description || '', x.serialNumber || null, x.status || 'available', x.location || '');
  return db.prepare('SELECT * FROM equipment WHERE id=?').get(r.lastInsertRowid);
}
function updateEquipment(id, x = {}, actorId) {
  const map = { assetCode:'asset_code', name:'name', description:'description', serialNumber:'serial_number', status:'status', location:'location' };
  const fields = [], params = { id, updatedAt: now() };
  for (const key of Object.keys(map)) if (x[key] !== undefined) { fields.push(map[key] + '=@' + key); params[key] = x[key]; }
  if (fields.length) db.prepare('UPDATE equipment SET ' + fields.join(',') + ',updated_at=@updatedAt WHERE id=@id').run(params);
  audit(actorId, 'equipment', id, 'updated', x);
  return db.prepare('SELECT * FROM equipment WHERE id=?').get(id);
}
function checkAvailability(ids, startsAt, endsAt) {
  ids = arr(ids).map(Number); if (!ids.length) return [];
  const q = ids.map(() => '?').join(',');
  return db.prepare("SELECT DISTINCT ri.equipment_id FROM request_items ri JOIN requests r ON r.id=ri.request_id JOIN time_windows w ON w.request_id=r.id WHERE ri.equipment_id IN (" + q + ") AND r.status IN ('pending','approved','pickup_pending','picked_up','overdue') AND w.status IN ('requested','approved') AND w.starts_at < ? AND w.ends_at > ?").all(...ids, startsAt, endsAt).map(x => x.equipment_id);
}
function requestView(id) {
  const r = db.prepare('SELECT r.*,u.krea_id,u.name AS requester_name,u.email AS requester_email FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.id=?').get(id);
  if (!r) return null;
  r.items = db.prepare('SELECT ri.*,e.asset_code,e.name,e.status AS equipment_status FROM request_items ri JOIN equipment e ON e.id=ri.equipment_id WHERE ri.request_id=?').all(id);
  r.windows = db.prepare('SELECT * FROM time_windows WHERE request_id=? ORDER BY starts_at').all(id);
  return r;
}
function createRequest(x = {}) {
  const ids = arr(x.equipmentIds || x.items).map(v => Number(v.id || v));
  if (!x.requesterId || !ids.length) throw new Error('requesterId and equipmentIds are required');
  const tx = db.transaction(() => {
    const user = db.prepare('SELECT * FROM users WHERE id=?').get(x.requesterId);
    if (!user) throw new Error('user not found'); if (user.banned) throw new Error('user is banned');
    const conflicts = checkAvailability(ids, x.pickupStartsAt, x.returnEndsAt);
    if (conflicts.length) throw new Error('equipment unavailable: ' + conflicts.join(','));
    const r = db.prepare('INSERT INTO requests(requester_id,purpose,academic_priority) VALUES (?,?,?)').run(x.requesterId, x.purpose || '', x.academicPriority || 0);
    for (const equipmentId of ids) { db.prepare('INSERT INTO request_items(request_id,equipment_id) VALUES (?,?)').run(r.lastInsertRowid, equipmentId); db.prepare("UPDATE equipment SET status='requested',updated_at=? WHERE id=?").run(now(), equipmentId); }
    if (x.pickupStartsAt && x.pickupEndsAt) db.prepare('INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)').run(r.lastInsertRowid, 'pickup', x.pickupStartsAt, x.pickupEndsAt);
    if (x.returnStartsAt && x.returnEndsAt) db.prepare('INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)').run(r.lastInsertRowid, 'return', x.returnStartsAt, x.returnEndsAt);
    audit(x.requesterId, 'request', r.lastInsertRowid, 'created', { equipmentIds:ids }); emit('request.created', 'request', r.lastInsertRowid, { equipmentIds:ids });
    return r.lastInsertRowid;
  });
  const requestId = tx();
  return requestView(requestId);
}
function setRequestStatus(id, status, actorId, details = {}) {
  const tx = db.transaction(() => {
    const r = db.prepare('SELECT * FROM requests WHERE id=?').get(id); if (!r) throw new Error('request not found');
    db.prepare('UPDATE requests SET status=?,rejection_reason=?,approval_notes=?,updated_at=? WHERE id=?').run(status, details.reason || r.rejection_reason, details.notes || r.approval_notes, now(), id);
    db.prepare('UPDATE request_items SET status=? WHERE request_id=?').run(status, id);
    if (status === 'approved') db.prepare("UPDATE equipment SET status='pickup_pending',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)").run(now(), id);
    if (status === 'rejected' || status === 'cancelled') db.prepare("UPDATE equipment SET status='available',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)").run(now(), id);
    audit(actorId, 'request', id, status, details); emit('request.' + status, 'request', id, details);
  });
  tx(); return requestView(id);
}
const approveRequest = (id, actorId, notes) => setRequestStatus(id, 'approved', actorId, { notes:notes || '' });
const rejectRequest = (id, actorId, reason) => setRequestStatus(id, 'rejected', actorId, { reason:reason || '' });
const cancelRequest = (id, actorId) => setRequestStatus(id, 'cancelled', actorId);
function scheduleWindow(x = {}) { const r = db.prepare('INSERT INTO time_windows(request_id,kind,starts_at,ends_at,status,notes) VALUES (?,?,?,?,?,?)').run(x.requestId, x.kind || 'pickup', x.startsAt, x.endsAt, x.status || 'requested', x.notes || ''); audit(x.actorId, 'request', x.requestId, 'window_scheduled', x); emit('window.updated', 'request', x.requestId, x); return db.prepare('SELECT * FROM time_windows WHERE id=?').get(r.lastInsertRowid); }
function recordPickup(x = {}) {
  const tx = db.transaction(() => { const ids = x.requestItemIds || db.prepare('SELECT id FROM request_items WHERE request_id=?').all(x.requestId).map(v => v.id); for (const id of ids) { db.prepare('INSERT INTO returns(request_item_id,picked_up_at) VALUES (?,?) ON CONFLICT(request_item_id) DO UPDATE SET picked_up_at=excluded.picked_up_at').run(id, x.pickedUpAt || now()); db.prepare("UPDATE request_items SET status='picked_up' WHERE id=?").run(id); } db.prepare("UPDATE requests SET status='picked_up',updated_at=? WHERE id=?").run(now(), x.requestId); db.prepare("UPDATE equipment SET status='picked_up',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)").run(now(), x.requestId); audit(x.actorId, 'request', x.requestId, 'pickup_confirmed', x); emit('pickup.confirmed', 'request', x.requestId, x); });
  tx(); return requestView(x.requestId);
}
function markNoShow(requestId, actorId) { db.prepare('UPDATE returns SET no_show=1 WHERE request_item_id IN (SELECT id FROM request_items WHERE request_id=?)').run(requestId); cancelRequest(requestId, actorId); emit('pickup.no_show', 'request', requestId); return requestView(requestId); }
const requestExtension = x => scheduleWindow({ ...x, kind:'extension', status:'requested' });
function recordReturn(x = {}) {
  const tx = db.transaction(() => { const ids = x.requestItemIds || db.prepare('SELECT id FROM request_items WHERE request_id=?').all(x.requestId).map(v => v.id); for (const id of ids) { db.prepare('INSERT INTO returns(request_item_id,returned_at,returned_flag,condition,damage_flag,notes) VALUES (?,?,1,?,?,?) ON CONFLICT(request_item_id) DO UPDATE SET returned_at=excluded.returned_at,returned_flag=1,condition=excluded.condition,damage_flag=excluded.damage_flag,notes=excluded.notes').run(id, x.returnedAt || now(), x.condition || '', x.damageFlag ? 1 : 0, x.notes || ''); db.prepare('UPDATE request_items SET status=? WHERE id=?').run(x.damageFlag ? 'damaged' : 'returned', id); } db.prepare("UPDATE requests SET status='returned',updated_at=? WHERE id=?").run(now(), x.requestId); db.prepare('UPDATE equipment SET status=?,updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)').run(x.damageFlag ? 'damaged' : 'available', now(), x.requestId); audit(x.actorId, 'request', x.requestId, 'return_recorded', x); emit('return.recorded', 'request', x.requestId, x); });
  tx(); return requestView(x.requestId);
}
function recordDamage(x = {}) { const r = db.prepare('INSERT INTO damage_reports(request_item_id,reported_by,description,severity) VALUES (?,?,?,?)').run(x.requestItemId, x.reportedBy || null, x.description, x.severity || 'unknown'); db.prepare("UPDATE request_items SET status='damaged' WHERE id=?").run(x.requestItemId); audit(x.reportedBy, 'request_item', x.requestItemId, 'damage_reported', x); emit('damage.reported', 'request_item', x.requestItemId, x); return db.prepare('SELECT * FROM damage_reports WHERE id=?').get(r.lastInsertRowid); }
function getDashboard() { return { pendingRequests:db.prepare("SELECT r.*,u.name AS requester_name FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.status='pending' ORDER BY r.academic_priority DESC,r.created_at").all(), windows:db.prepare('SELECT w.*,r.status,u.name AS requester_name FROM time_windows w JOIN requests r ON r.id=w.request_id JOIN users u ON u.id=r.requester_id ORDER BY w.starts_at').all(), equipment:db.prepare('SELECT * FROM equipment ORDER BY name COLLATE NOCASE').all() }; }
const getAuditHistory = (type, id) => db.prepare('SELECT * FROM audit_log WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC').all(type, id);
const getOutbox = (limit = 100) => db.prepare('SELECT * FROM outbox_events WHERE published_at IS NULL ORDER BY id LIMIT ?').all(Math.min(Math.max(Number(limit) || 100, 1), 1000));
function markEventsPublished(ids) { const tx = db.transaction(() => arr(ids).forEach(id => db.prepare('UPDATE outbox_events SET published_at=? WHERE id=?').run(now(), id))); tx(); }
function find(f = {}) { const w = [], p = {}; if (f.status) { w.push('status=@status'); p.status = f.status; } if (f.q) { w.push('(name LIKE @q OR asset_code LIKE @q OR serial_number LIKE @q OR description LIKE @q)'); p.q = '%' + f.q + '%'; } p.limit = Math.min(Math.max(Number(f.limit) || 100, 1), 1000); p.offset = Math.max(Number(f.offset) || 0, 0); return db.prepare('SELECT * FROM equipment ' + (w.length ? 'WHERE ' + w.join(' AND ') : '') + ' ORDER BY name COLLATE NOCASE LIMIT @limit OFFSET @offset').all(p); }
const stats = () => db.prepare('SELECT status,COUNT(*) AS count FROM equipment GROUP BY status ORDER BY status').all();
const close = () => db.close();

module.exports = { db, dbPath, addUser, updateUser, banUser, unbanUser, addEquipment, updateEquipment,
  createRequest, checkAvailability, approveRequest, rejectRequest, cancelRequest, scheduleWindow,
  recordPickup, markNoShow, requestExtension, recordReturn, recordDamage, getDashboard,
  getAuditHistory, getOutbox, markEventsPublished, find, stats, close };
