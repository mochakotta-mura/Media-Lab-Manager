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
import secrets
import sys
import time
from datetime import datetime
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
sessions: dict[str, tuple[float, dict]] = {}
pin_hashes: dict[str, str] = {}


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


def public_user(user: dict, account_type: str | None = None) -> dict:
    return {"id": user["id"], "kreaId": user["krea_id"], "name": user["name"],
            "email": user.get("email"), "role": account_type or user.get("role")}


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
        token = auth[7:].strip() if auth.startswith("Bearer ") else self.cookies().get("mlm_session")
        session = sessions.get(token)
        if not session:
            return None
        expires, user = session
        if expires < time.time():
            sessions.pop(token, None)
            return None
        sessions[token] = (time.time() + SESSION_SECONDS, user)
        return user

    def require_user(self):
        user = self.current_user()
        if not user:
            raise ApiError("You must sign in first", 401)
        return user

    def require_staff(self):
        user = self.require_user()
        if user.get("role") not in {"faculty", "media_lab", "admin", "staff"}:
            raise ApiError("Staff access is required", 403)
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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

    def route(self, method, path, data):
        if method == "POST" and path == "/api/auth/login":
            return self.login(data)
        if method == "POST" and path == "/api/auth/logout":
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.startswith("Bearer ") else self.cookies().get("mlm_session")
            sessions.pop(token, None)
            return self.send_json(200, {"ok": True}, {"Set-Cookie": "mlm_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})
        if method == "GET" and path == "/api/auth/me":
            user = self.require_user()
            return self.send_json(200, {"user": user})

        user = self.require_user()
        if method == "GET" and path == "/api/equipment":
            filters = {key: values[0] for key, values in data.items()}
            return self.send_json(200, db.find(filters))
        if method == "GET" and path == "/api/equipment/stats":
            self.require_staff()
            return self.send_json(200, db.stats())
        if method == "POST" and path == "/api/users":
            self.require_staff()
            return self.send_json(201, db.add_user(data))
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
            if filters.get("requesterId") and int(filters["requesterId"]) != user["id"]:
                self.require_staff()
            if user.get("role") not in {"faculty", "media_lab", "admin", "staff"}:
                filters["requesterId"] = str(user["id"])
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
        account = str(data.get("accountType", "")).lower().strip()
        email = str(data.get("email", "")).lower().strip()
        pin = str(data.get("pin", ""))
        if account not in {"student", "faculty", "media_lab"}:
            raise ApiError("Choose Student, Faculty, or Media Lab")
        domain = "@krea.ac.in" if account == "student" else "@krea.edu.in"
        if not email.endswith(domain):
            raise ApiError(f"This account must use {domain}")
        if len(pin) != 4 or not pin.isdigit():
            raise ApiError("PIN must be exactly 4 digits")
        row = db.connection.execute("SELECT * FROM users WHERE email=? LIMIT 1", (email,)).fetchone()
        user = dict(row) if row else None
        if not user:
            user = db.add_user({"kreaId": email, "name": email.split("@", 1)[0], "email": email, "role": account})
        encoded = pin_hashes.get(email)
        if encoded and not verify_pin(pin, encoded):
            raise ApiError("Invalid email or PIN")
        if not encoded:
            pin_hashes[email] = hash_pin(pin)
        if user.get("banned"):
            raise ApiError("This account is banned")
        safe = public_user(user, account)
        token = secrets.token_hex(32)
        sessions[token] = (time.time() + SESSION_SECONDS, safe)
        return self.send_json(200, {"user": safe, "sessionToken": token}, {
            "Set-Cookie": f"mlm_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_SECONDS}"})

    def static_file(self, path):
        path = "/index.html" if path in {"", "/"} else path
        if path.startswith("/pages/") and not self.current_user():
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
