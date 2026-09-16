"""Framework-free Media Lab Manager API and static frontend server.

Run from the repository root with:
    python3 MLM.integration/server/server.py

The server uses the repository's mlm_database_commands.Database facade. It
does not create a second SQLite connection or require third-party packages.
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "MLM.Database"))
from mlm_database_commands import Database  # noqa: E402

FRONTEND = ROOT / "Media Lab Front"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "3000"))
SESSION_SECONDS = 8 * 60 * 60
db = Database()
SESSION_COOKIE = "mlm_session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${value.hex()}"


def verify_pin(pin: str, encoded: str) -> bool:
    try:
        scheme, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def public_user(user: dict) -> dict:
    return {"id": user["id"], "kreaId": user["krea_id"], "name": user["name"],
            "email": user.get("email"), "role": user.get("role", "student")}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_header(token: str, max_age: int) -> str:
    secure = "; Secure" if COOKIE_SECURE else ""
    return f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}"


def now_epoch() -> float:
    return time.time()


def account_lock(user: dict | None) -> float:
    try:
        return float((user or {}).get("locked_until") or 0)
    except (TypeError, ValueError):
        return 0


def attempt_row(ip: str, email: str):
    return db.connection.execute(
        "SELECT * FROM auth_attempts WHERE ip_address=? AND email=?", (ip, email)
    ).fetchone()


def check_login_allowed(ip: str, email: str, user: dict | None):
    now = now_epoch()
    if account_lock(user) > now:
        raise ApiError("This account is temporarily locked. Try again later.", 429)
    row = attempt_row(ip, email)
    if row and row["locked_until"] and float(row["locked_until"]) > now:
        raise ApiError("Too many failed attempts. Try again later.", 429)
    if row and now - float(row["window_started_at"]) >= LOGIN_WINDOW_SECONDS:
        db.connection.execute(
            "UPDATE auth_attempts SET failed_attempts=0,window_started_at=?,locked_until=NULL,updated_at=? WHERE id=?",
            (now, now, row["id"]),
        )
        db.connection.commit()


def record_failed_login(ip: str, email: str, user: dict | None):
    now = now_epoch()
    row = attempt_row(ip, email)
    failures = 1
    if row and now - float(row["window_started_at"]) < LOGIN_WINDOW_SECONDS:
        failures = int(row["failed_attempts"]) + 1
    locked_until = now + LOGIN_LOCK_SECONDS if failures >= LOGIN_MAX_ATTEMPTS else None
    db.connection.execute(
        """INSERT INTO auth_attempts(ip_address,email,failed_attempts,window_started_at,locked_until,updated_at)
        VALUES (?,?,?,?,?,?) ON CONFLICT(ip_address,email) DO UPDATE SET
        failed_attempts=excluded.failed_attempts,window_started_at=excluded.window_started_at,
        locked_until=excluded.locked_until,updated_at=excluded.updated_at""",
        (ip, email, failures, now if not row or now - float(row["window_started_at"]) >= LOGIN_WINDOW_SECONDS else row["window_started_at"], locked_until, now),
    )
    if user:
        db.connection.execute(
            "UPDATE users SET failed_pin_attempts=?,locked_until=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (failures, str(locked_until) if locked_until else None, user["id"]),
        )
    db.connection.commit()


def clear_failed_logins(ip: str, email: str, user: dict):
    db.connection.execute("DELETE FROM auth_attempts WHERE ip_address=? AND email=?", (ip, email))
    db.connection.execute(
        "UPDATE users SET failed_pin_attempts=0,locked_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (user["id"],),
    )
    db.connection.commit()


def iso_date(value: str, field: str) -> datetime:
    if not value:
        raise ApiError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ApiError(f"{field} must be an ISO-8601 date") from error
    if parsed.tzinfo is None:
        raise ApiError(f"{field} must include a timezone")
    return parsed


def request_view(request_id: int):
    return db._request_view(request_id)


def request_owner(request_id: int):
    request = request_view(request_id)
    if not request:
        raise ApiError("Request not found", 404)
    return request


def request_list(filters: dict):
    clauses, values = [], []
    if filters.get("requesterId"):
        clauses.append("requester_id=?")
        values.append(int(filters["requesterId"]))
    if filters.get("status"):
        clauses.append("status=?")
        values.append(str(filters["status"]))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.connection.execute(
        f"SELECT id FROM requests{where} ORDER BY created_at DESC", values).fetchall()
    return [request_view(row["id"]) for row in rows]


def ensure_available(equipment_ids, starts_at: str, ends_at: str):
    """Reject any interval overlap, including partial overlaps."""
    ids = [int(value.get("id", value) if isinstance(value, dict) else value) for value in equipment_ids]
    if not ids:
        raise ApiError("At least one equipment item is required")
    marks = ",".join("?" for _ in ids)
    unavailable = db.connection.execute(
        f"SELECT id FROM equipment WHERE id IN ({marks}) AND status <> 'available'", ids
    ).fetchall()
    if unavailable:
        raise ApiError("equipment unavailable: " + ",".join(str(row["id"]) for row in unavailable), 409)
    rows = db.connection.execute(
        f"""SELECT DISTINCT ri.equipment_id FROM request_items ri
        JOIN requests r ON r.id=ri.request_id
        JOIN time_windows w ON w.request_id=r.id
        WHERE ri.equipment_id IN ({marks})
          AND r.status IN ('pending','approved','pickup_pending','picked_up','overdue')
          AND w.status IN ('requested','approved')
          AND w.starts_at < ? AND w.ends_at > ?""",
        [*ids, ends_at, starts_at]).fetchall()
    if rows:
        raise ApiError("equipment unavailable: " + ",".join(str(row["equipment_id"]) for row in rows), 409)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "MediaLabManager/1.0"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, status: int, value, headers: dict | None = None):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in {"null", f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def fail(self, error):
        status = error.status if isinstance(error, ApiError) else 500
        self.send_json(status, {"error": str(error)})

    def cookies(self):
        values = {}
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                values[key] = value
        return values

    def current_user(self):
        auth = self.headers.get("Authorization", "")
        # Bearer auth is intentionally not accepted. Sessions are cookie-only.
        if auth:
            return None
        token = self.cookies().get(SESSION_COOKIE)
        if not token:
            return None
        row = db.connection.execute(
            "SELECT u.*,s.id AS session_id,s.expires_at AS session_expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
            (token_hash(token),),
        ).fetchone()
        if not row or float(row["session_expires_at"]) < now_epoch() or row["banned"]:
            if row:
                db.connection.execute("DELETE FROM sessions WHERE id=?", (row["session_id"],))
                db.connection.commit()
            return None
        expires = now_epoch() + SESSION_SECONDS
        db.connection.execute("UPDATE sessions SET expires_at=?,last_seen_at=? WHERE id=?", (expires, now_epoch(), row["session_id"]))
        db.connection.commit()
        return public_user(dict(row))

    def require_user(self):
        user = self.current_user()
        if not user:
            raise ApiError("You must sign in first", 401)
        return user

    def require_staff(self):
        user = self.require_user()
        if user.get("role") not in {"faculty", "media_lab", "admin", "staff"} or not str(user.get("email", "")).endswith("@krea.edu.in"):
            raise ApiError("Staff access is required", 403)
        return user

    def require_admin(self):
        user = self.require_user()
        if user.get("role") != "admin" or not str(user.get("email", "")).endswith("@krea.edu.in"):
            raise ApiError("Administrator access is required", 403)
        return user

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ApiError("Request body is too large", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ApiError("Invalid JSON") from error
        if not isinstance(value, dict):
            raise ApiError("JSON body must be an object")
        return value

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-MLM-CSRF")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, OPTIONS")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.route("GET", parsed.path, parse_qs(parsed.query))
            else:
                self.static_file(parsed.path)
        except Exception as error:
            self.fail(error)

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                raise ApiError("Route not found", 404)
            self.route("POST", parsed.path, self.read_body())
        except Exception as error:
            self.fail(error)

    def do_PATCH(self):
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                raise ApiError("Route not found", 404)
            self.route("PATCH", parsed.path, self.read_body())
        except Exception as error:
            self.fail(error)

    def do_PUT(self):
        self.do_PATCH()

    def route(self, method, path, data):
        if method == "POST" and path == "/api/auth/login":
            return self.login(data)
        if method == "POST" and path == "/api/auth/logout":
            if self.headers.get("X-MLM-CSRF") != "1":
                raise ApiError("CSRF check failed", 403)
            token = self.cookies().get(SESSION_COOKIE)
            if token:
                db.connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
                db.connection.commit()
            return self.send_json(200, {"ok": True}, {"Set-Cookie": cookie_header("", 0)})
        if method == "GET" and path == "/api/auth/me":
            user = self.require_user()
            return self.send_json(200, {"user": user})

        if method == "POST" and self.headers.get("X-MLM-CSRF") != "1":
            raise ApiError("CSRF check failed", 403)
        user = self.require_user()
        if method == "GET" and path == "/api/equipment":
            filters = {key: values[0] for key, values in data.items()}
            return self.send_json(200, db.find(filters))
        if method == "GET" and path == "/api/equipment/stats":
            self.require_staff()
            return self.send_json(200, db.stats())
        if method == "POST" and path == "/api/equipment":
            self.require_staff()
            return self.send_json(201, db.add_equipment(data))
        if method in {"PATCH", "PUT"} and len(path.split("/")) == 4 and path.split("/")[2] == "equipment":
            self.require_staff()
            return self.send_json(200, db.update_equipment(int(path.split("/")[3]), data, user["id"]))
        if method == "GET" and path == "/api/settings":
            self.require_admin()
            return self.send_json(200, db.get_settings())
        if method in {"PATCH", "PUT"} and path == "/api/settings":
            self.require_admin()
            return self.send_json(200, db.update_settings(data))
        if method == "POST" and path == "/api/users":
            self.require_admin()
            return self.send_json(201, db.add_user({**data, "role": "student"}))
        if method == "GET" and path == "/api/users":
            self.require_staff()
            return self.send_json(200, db.list_users())
        if method == "POST" and path == "/api/requests":
            body = dict(data)
            body["requesterId"] = user["id"]
            for start, end in (("pickupStartsAt", "pickupEndsAt"), ("returnStartsAt", "returnEndsAt")):
                start_date = iso_date(body.get(start), start)
                end_date = iso_date(body.get(end), end)
                if end_date <= start_date:
                    raise ApiError(f"{end} must be after {start}")
            ensure_available(body.get("equipmentIds", body.get("items", [])), body["pickupStartsAt"], body["returnEndsAt"])
            return self.send_json(201, db.create_request(body))
        if method == "GET" and path == "/api/requests":
            filters = {key: values[0] for key, values in data.items()}
            is_staff = user.get("role") in {"faculty", "media_lab", "admin", "staff"}
            if not is_staff:
                filters["requesterId"] = str(user["id"])
            elif filters.get("requesterId"):
                filters["requesterId"] = str(int(filters["requesterId"]))
            return self.send_json(200, request_list(filters))

        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) >= 4 and parts[1] == "requests":
            request_id = int(parts[2])
            request = request_owner(request_id)
            action = parts[3]
            is_staff = user.get("role") in {"faculty", "media_lab", "admin", "staff"}
            if action == "cancel":
                if request["requester_id"] != user["id"] and not is_staff:
                    raise ApiError("You do not own this request", 403)
                return self.send_json(200, db.cancel_request(request_id, user["id"]))
            if action in {"approve", "reject", "windows", "pickup"} and not is_staff:
                raise ApiError("Staff access is required", 403)
            if action == "approve":
                return self.send_json(200, db.approve_request(request_id, user["id"], data.get("notes", "")))
            if action == "reject":
                return self.send_json(200, db.reject_request(request_id, user["id"], data.get("reason", "")))
            if action == "windows":
                starts_at = iso_date(data.get("startsAt"), "startsAt")
                ends_at = iso_date(data.get("endsAt"), "endsAt")
                if ends_at <= starts_at:
                    raise ApiError("endsAt must be after startsAt")
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(201, db.schedule_window(body))
            if action == "extensions":
                if request["requester_id"] != user["id"] and not is_staff:
                    raise ApiError("You do not own this request", 403)
                starts_at = iso_date(data.get("startsAt"), "startsAt")
                ends_at = iso_date(data.get("endsAt"), "endsAt")
                if ends_at <= starts_at:
                    raise ApiError("endsAt must be after startsAt")
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(201, db.request_extension(body))
            if action == "pickup":
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(200, db.record_pickup(body))
            if action == "return":
                if request["requester_id"] != user["id"] and not is_staff:
                    raise ApiError("You do not own this request", 403)
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(200, db.record_return(body))
        if len(parts) == 4 and parts[1] == "request-items" and parts[3] == "damage":
            self.require_staff()
            body = {**data, "requestItemId": int(parts[2]), "reportedBy": user["id"]}
            if not body.get("description"):
                raise ApiError("description is required")
            return self.send_json(201, db.record_damage(body))
        if method == "GET" and len(parts) == 4 and parts[1] == "audit":
            self.require_staff()
            return self.send_json(200, db.get_audit_history(parts[2], int(parts[3])))
        if method == "GET" and path == "/api/dashboard":
            self.require_staff()
            return self.send_json(200, db.get_dashboard())
        if method == "GET" and path == "/api/outbox":
            self.require_staff()
            return self.send_json(200, db.get_outbox())
        raise ApiError("API route not found", 404)

    def login(self, data):
        email = str(data.get("email", "")).lower().strip()
        pin = str(data.get("pin", ""))
        if not re.match(r"^[^@\s]+@krea\.(ac\.in|edu\.in)$", email):
            raise ApiError("Use a valid @krea.ac.in or @krea.edu.in email address")
        if len(pin) != 4 or not pin.isdigit():
            raise ApiError("PIN must be exactly 4 digits")
        row = db.connection.execute("SELECT * FROM users WHERE email=? LIMIT 1", (email,)).fetchone()
        user = dict(row) if row else None
        if not user:
            user = db.add_user({"kreaId": email, "name": email.split("@", 1)[0], "email": email, "role": "student"})
            user["pin_hash"] = ""
        check_login_allowed(self.client_address[0], email, user)
        encoded = user.get("pin_hash") or ""
        if encoded:
            if not verify_pin(pin, encoded):
                record_failed_login(self.client_address[0], email, user)
                raise ApiError("Invalid email or PIN", 401)
        else:
            db.connection.execute("UPDATE users SET pin_hash=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (hash_pin(pin), user["id"]))
            db.connection.commit()
        if user.get("banned"):
            raise ApiError("This account is banned")
        clear_failed_logins(self.client_address[0], email, user)
        safe = public_user(user)
        token = secrets.token_hex(32)
        db.connection.execute(
            "INSERT INTO sessions(token_hash,user_id,expires_at,last_seen_at) VALUES (?,?,?,?)",
            (token_hash(token), user["id"], now_epoch() + SESSION_SECONDS, now_epoch()),
        )
        db.connection.commit()
        return self.send_json(200, {"user": safe}, {"Set-Cookie": cookie_header(token, SESSION_SECONDS)})

    def static_file(self, path):
        path = "/index.html" if path in {"", "/"} else path
        user = self.current_user()
        if path.startswith("/pages/admin/"):
            if not user or user.get("role") not in {"faculty", "media_lab", "staff", "admin"} or not str(user.get("email", "")).endswith("@krea.edu.in"):
                self.send_response(302); self.send_header("Location", "/pages/catalog.html"); self.end_headers(); return
            if path.endswith("/settings.html") and user.get("role") != "admin":
                self.send_response(302); self.send_header("Location", "/pages/catalog.html"); self.end_headers(); return
        if path.startswith("/pages/") and not user:
            self.send_response(302); self.send_header("Location", "/"); self.end_headers(); return
        target = (FRONTEND / unquote(path.lstrip("/"))).resolve()
        if FRONTEND.resolve() not in target.parents or not target.is_file():
            raise ApiError("Page not found", 404)
        types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
                 ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml"}
        self.send_response(200)
        self.send_header("Content-Type", types.get(target.suffix, "application/octet-stream"))
        self.end_headers()
        self.wfile.write(target.read_bytes())


def main():
    server = http.server.HTTPServer((HOST, PORT), Handler)
    print(f"Media Lab Manager listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        db.close()


if __name__ == "__main__":
    main()
