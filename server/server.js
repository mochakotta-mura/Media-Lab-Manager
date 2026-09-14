'use strict';

const http = require('node:http');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const dbModule = require('../MLM.Database/MLM.Database.Commands');

const db = dbModule.db;
const frontendRoot = path.join(__dirname, '..', 'Media Lab Frontend');
const port = Number(process.env.PORT || 3000);
const sessions = new Map();

function applyCors(req, res) {
  const origin = req.headers.origin;
  if (origin === 'null' || origin === `http://localhost:${port}` || origin === `http://127.0.0.1:${port}`) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Vary', 'Origin');
  }
}

function json(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(body);
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; if (body.length > 1024 * 1024) reject(new Error('Request too large')); });
    req.on('end', () => { try { resolve(body ? JSON.parse(body) : {}); } catch { reject(new Error('Invalid JSON')); } });
    req.on('error', reject);
  });
}

function cookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').filter(Boolean).map(value => {
    const index = value.indexOf('=');
    return [value.slice(0, index).trim(), decodeURIComponent(value.slice(index + 1).trim())];
  }));
}

function sessionUser(req) {
  const authorization = String(req.headers.authorization || '');
  const bearer = authorization.startsWith('Bearer ') ? authorization.slice(7).trim() : '';
  const token = bearer || cookies(req).mlm_session;
  const session = token && sessions.get(token);
  if (!session || session.expiresAt < Date.now()) return null;
  session.expiresAt = Date.now() + 8 * 60 * 60 * 1000;
  return session.user;
}

function requireUser(req, res) {
  const user = sessionUser(req);
  if (!user) { json(res, 401, { error: 'You must sign in first.' }); return null; }
  return user;
}

const accountTypes = new Set(['student', 'faculty', 'media_lab']);
function hashPin(pin) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(pin, salt, 32, { N: 16384, r: 8, p: 1 }).toString('hex');
  return `scrypt$${salt}$${hash}`;
}
function verifyPin(pin, encoded) {
  if (typeof encoded !== 'string' || !encoded.startsWith('scrypt$')) return false;
  const [, salt, expectedHex] = encoded.split('$');
  if (!salt || !/^[0-9a-f]{64}$/i.test(expectedHex || '')) return false;
  const actual = crypto.scryptSync(pin, salt, 32, { N: 16384, r: 8, p: 1 });
  return crypto.timingSafeEqual(actual, Buffer.from(expectedHex, 'hex'));
}
function validateLogin(body) {
  const accountType = String(body.accountType || '').trim().toLowerCase();
  const email = String(body.email || '').trim().toLowerCase();
  const pin = String(body.pin || '');
  if (!accountTypes.has(accountType)) throw new Error('Choose Student, Faculty, or Media Lab.');
  if (!/^\S+@\S+$/.test(email)) throw new Error('Enter a valid Krea email address.');
  const allowedDomain = accountType === 'student' ? '@krea.ac.in' : '@krea.edu.in';
  if (!email.endsWith(allowedDomain)) throw new Error(`${accountType === 'student' ? 'Student' : accountType === 'faculty' ? 'Faculty' : 'Media Lab'} accounts must use ${allowedDomain}.`);
  if (!/^\d{4}$/.test(pin)) throw new Error('PIN must be exactly 4 digits.');
  return { accountType, email, pin };
}
function publicUser(user, accountType) {
  return { id: user.id, kreaId: user.krea_id, name: user.name, email: user.email, role: accountType || user.role };
}
function authenticatePin(body) {
  const { accountType, email, pin } = validateLogin(body);
  let user = db.prepare('SELECT * FROM users WHERE email = ? LIMIT 1').get(email);
  if (!user) {
    user = dbModule.addUser({ kreaId: email, name: email.split('@')[0], email, role: accountType, pinHash: hashPin(pin) });
  } else if (!user.pin_hash) {
    throw new Error('This account has no PIN configured. Ask the Media Lab administrator to provision it.');
  } else if (!verifyPin(pin, user.pin_hash)) {
    throw new Error('Invalid email or PIN.');
  }
  if (user.banned) throw new Error('This account is banned.');
  return publicUser(user, accountType);
}

async function api(req, res, pathname) {
  if (req.method === 'POST' && pathname === '/api/auth/login') {
    try {
      const user = authenticatePin(await parseBody(req));
      const token = crypto.randomBytes(32).toString('hex');
      sessions.set(token, { user, expiresAt: Date.now() + 8 * 60 * 60 * 1000 });
      res.setHeader('Set-Cookie', `mlm_session=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800`);
      return json(res, 200, { user, sessionToken: token });
    } catch (error) { return json(res, 400, { error: error.message }); }
  }
  if (req.method === 'POST' && pathname === '/api/auth/logout') {
    const authorization = String(req.headers.authorization || '');
    const bearer = authorization.startsWith('Bearer ') ? authorization.slice(7).trim() : '';
    const token = bearer || cookies(req).mlm_session; if (token) sessions.delete(token);
    res.setHeader('Set-Cookie', 'mlm_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0');
    return json(res, 200, { ok: true });
  }
  if (req.method === 'GET' && pathname === '/api/auth/me') {
    const user = sessionUser(req); return user ? json(res, 200, { user }) : json(res, 401, { error: 'Not signed in.' });
  }
  const user = requireUser(req, res); if (!user) return;
  if (req.method === 'GET' && pathname === '/api/equipment') {
    const url = new URL(req.url, 'http://localhost');
    return json(res, 200, dbModule.find({ q: url.searchParams.get('q') || '', status: url.searchParams.get('status') || undefined, limit: url.searchParams.get('limit') || 100 }));
  }
  if (req.method === 'GET' && pathname === '/api/equipment/stats') return json(res, 200, dbModule.stats());
  if (req.method === 'POST' && pathname === '/api/requests') {
    try { const body = await parseBody(req); return json(res, 201, dbModule.createRequest({ ...body, requesterId: user.id })); }
    catch (error) { return json(res, 400, { error: error.message }); }
  }
  return json(res, 404, { error: 'API route not found.' });
}

function staticFile(req, res) {
  let pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  if (pathname === '/') pathname = '/index.html';
  if (pathname.startsWith('/pages/') && !sessionUser(req)) {
    res.writeHead(302, { Location: '/' });
    return res.end();
  }
  const file = path.resolve(frontendRoot, '.' + pathname);
  if (!file.startsWith(path.resolve(frontendRoot) + path.sep)) return json(res, 403, { error: 'Forbidden' });
  fs.readFile(file, (error, content) => {
    if (error) return json(res, 404, { error: 'Page not found.' });
    const type = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.png':'image/png', '.jpg':'image/jpeg' }[path.extname(file)] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type + '; charset=utf-8' }); res.end(content);
  });
}

const server = http.createServer((req, res) => {
  applyCors(req, res);
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (pathname.startsWith('/api/')) return api(req, res, pathname).catch(error => json(res, 500, { error: error.message }));
  return staticFile(req, res);
});
server.listen(port, () => console.log(`Media Lab Manager listening on http://localhost:${port}`));
process.on('SIGINT', () => { dbModule.close(); server.close(() => process.exit(0)); });
