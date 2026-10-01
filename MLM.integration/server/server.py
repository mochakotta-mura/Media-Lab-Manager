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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "MLM.Database"))
from mlm_database_commands import Database  # noqa: E402
from services.authentication_service import AuthenticationService  # noqa: E402
from services.equipment_service import EquipmentService  # noqa: E402
from services.notification_service import NotificationService  # noqa: E402
from services.request_service import RequestService  # noqa: E402

FRONTEND = ROOT / "Media Lab Front"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "3000"))
SESSION_SECONDS = 8 * 60 * 60
db = Database()
SESSION_COOKIE = "mlm_session"
COOKIE_SECURE = os.environ.get(
    "COOKIE_SECURE", "true" if HOST not in {"127.0.0.1", "localhost"} else "false"
).lower() not in {"0", "false", "no"}
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
STAFF_ROLES = {"faculty", "media_lab", "staff", "admin"}
ADMIN_EMAILS = {"bing@krea.edu.in", "demo.admin@krea.edu.in"}

ROLE_BY_EMAIL_DOMAIN = {
    "krea.ac.in": "student",
    "krea.edu.in": "faculty",
    "krea.medialab.in": "admin",
}
STAFF_EMAIL_DOMAINS = {"krea.edu.in", "krea.medialab.in"}


def ensure_return_submission_schema():
    """Create the return-submission records used by two-party verification."""
    db.connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS return_submissions (
          id INTEGER PRIMARY KEY,
          request_id INTEGER NOT NULL UNIQUE REFERENCES requests(id) ON DELETE CASCADE,
          submitted_by INTEGER NOT NULL REFERENCES users(id),
          submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          claimed_returned_at TEXT NOT NULL,
          student_condition TEXT DEFAULT '',
          damage_description TEXT DEFAULT '',
          missing_items TEXT DEFAULT '',
          photo_references TEXT DEFAULT '[]',
          verification_status TEXT NOT NULL DEFAULT 'return_submitted'
            CHECK(verification_status IN ('return_submitted','verified_returned','verified_damaged','missing_items','disputed_return')),
          verified_at TEXT,
          verified_by INTEGER REFERENCES users(id),
          actual_returned_at TEXT,
          staff_condition TEXT DEFAULT '',
          staff_notes TEXT DEFAULT '',
          verification_photos TEXT DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS idx_return_submissions_status
          ON return_submissions(verification_status);
        """
    )
    db.connection.commit()


ensure_return_submission_schema()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        """Represent an API error with an HTTP status code."""
        super().__init__(message)
        self.status = status


def hash_pin(pin: str) -> str:
    """Create a salted scrypt hash for a PIN."""
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${value.hex()}"


def verify_pin(pin: str, encoded: str) -> bool:
    """Verify a PIN against an encoded scrypt hash."""
    try:
        scheme, salt, expected = encoded.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def public_user(user: dict) -> dict:
    """Return the safe user fields exposed to the frontend."""
    email = str(user.get("email", "")).lower()
    stored_role = str(user.get("role") or "").lower()
    if is_admin_email(email):
        role = "admin"
    elif stored_role == "admin":
        role = role_for_email(email) or "student"
    else:
        role = stored_role or role_for_email(email) or "student"
    return {"id": user["id"], "kreaId": user["krea_id"], "name": user["name"],
            "email": user.get("email"), "role": role}


def is_staff(user: dict) -> bool:
    """Check whether a user may access staff operations."""
    return user.get("role") in STAFF_ROLES and is_staff_email(user.get("email"))


def is_admin(user: dict) -> bool:
    """Check whether a user may access administrator operations."""
    email = str(user.get("email", "")).lower()
    return is_admin_email(email)


def is_admin_email(email: str | None) -> bool:
    """Check the allowlist and domain reserved for administrator access."""
    normalized = str(email or "").lower()
    return normalized in ADMIN_EMAILS or normalized.endswith("@krea.medialab.in")


def role_for_email(email: str) -> str | None:
    normalized = str(email or "").lower()
    if is_admin_email(normalized):
        return "admin"
    return ROLE_BY_EMAIL_DOMAIN.get(normalized.rsplit("@", 1)[-1])


def is_staff_email(email: str | None) -> bool:
    return str(email or "").lower().rsplit("@", 1)[-1] in STAFF_EMAIL_DOMAINS


def token_hash(token: str) -> str:
    """Hash a session token before database storage or lookup."""
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_header(token: str, max_age: int) -> str:
    """Build the session cookie header."""
    secure = "; Secure" if COOKIE_SECURE else ""
    return f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}"


def now_epoch() -> float:
    """Return the current Unix timestamp."""
    return time.time()


def account_lock(user: dict | None) -> float:
    """Read a user's temporary lock expiry timestamp."""
    try:
        return float((user or {}).get("locked_until") or 0)
    except (TypeError, ValueError):
        return 0


def attempt_row(ip: str, email: str):
    """Load login-attempt data for an IP and email pair."""
    return db.connection.execute(
        "SELECT * FROM auth_attempts WHERE ip_address=? AND email=?", (ip, email)
    ).fetchone()


def check_login_allowed(ip: str, email: str, user: dict | None):
    """Reject accounts or IPs currently blocked by login limits."""
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
    """Record a failed login and apply lockout thresholds."""
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
    """Clear failed-login counters after successful authentication."""
    db.connection.execute("DELETE FROM auth_attempts WHERE ip_address=? AND email=?", (ip, email))
    db.connection.execute(
        "UPDATE users SET failed_pin_attempts=0,locked_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (user["id"],),
    )
    db.connection.commit()


def iso_date(value: str, field: str) -> datetime:
    """Parse and validate a timezone-aware ISO-8601 date."""
    if not value:
        raise ApiError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ApiError(f"{field} must be an ISO-8601 date") from error
    if parsed.tzinfo is None:
        raise ApiError(f"{field} must include a timezone")
    return parsed


def validate_pickup_slot(request_id: int, starts_at: str, ends_at: str):
    """Validate an administrator slot against the student's requested pickup."""
    starts = iso_date(starts_at, "startsAt")
    ends = iso_date(ends_at, "endsAt")
    if ends <= starts:
        raise ApiError("endsAt must be after startsAt")
    requested = db.connection.execute(
        "SELECT starts_at FROM time_windows WHERE request_id=? AND kind='pickup' AND status='requested' ORDER BY id LIMIT 1",
        (request_id,),
    ).fetchone()
    if requested is None:
        raise ApiError("Original pickup slot not found", 409)
    requested_start = iso_date(requested["starts_at"], "requested pickup start")
    earliest = requested_start - timedelta(hours=24)
    latest = requested_start - timedelta(minutes=20)
    if starts < earliest or starts > latest:
        raise ApiError("Pickup slot must start between 24 hours and 20 minutes before the requested pickup time")
    if ends > requested_start:
        raise ApiError("Pickup slot must end by the requested pickup time")


def request_view(request_id: int):
    """Return one request with its items, windows, and return submission."""
    request = db._request_view(request_id)
    if request:
        request["return_submission"] = return_submission_view(request_id)
    return request


def return_submission_view(request_id: int):
    """Return the student submission and staff verification details."""
    row = db.connection.execute(
        "SELECT * FROM return_submissions WHERE request_id=?", (request_id,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    for field in ("photo_references", "verification_photos"):
        try:
            result[field] = json.loads(result[field] or "[]")
        except (TypeError, json.JSONDecodeError):
            result[field] = []
    return result


def return_payload(data: dict, request_id: int, user_id: int):
    """Normalize return-submission fields and attach the authenticated user."""
    claimed = data.get("claimedReturnedAt") or data.get("returnedAt")
    iso_date(claimed, "claimedReturnedAt")
    photos = data.get("photoReferences", data.get("photos", []))
    if not isinstance(photos, list):
        raise ApiError("photoReferences must be a list")
    return {
        "requestId": request_id,
        "submittedBy": user_id,
        "claimedReturnedAt": claimed,
        "studentCondition": data.get("studentCondition", data.get("condition", "")),
        "damageDescription": data.get("damageDescription", data.get("notes", "")),
        "missingItems": data.get("missingItems", ""),
        "photoReferences": photos,
    }


def create_return_submission(data: dict):
    """Store or replace a student's pending return submission."""
    existing = db.connection.execute(
        "SELECT verification_status FROM return_submissions WHERE request_id=?", (data["requestId"],)
    ).fetchone()
    if existing and existing["verification_status"] in {"verified_returned", "verified_damaged", "missing_items"}:
        raise ApiError("This return has already been verified", 409)
    db.connection.execute(
        """INSERT INTO return_submissions
           (request_id,submitted_by,claimed_returned_at,student_condition,damage_description,missing_items,photo_references,verification_status)
           VALUES (?,?,?,?,?,?,?,'return_submitted')
           ON CONFLICT(request_id) DO UPDATE SET
             submitted_by=excluded.submitted_by,submitted_at=CURRENT_TIMESTAMP,
             claimed_returned_at=excluded.claimed_returned_at,student_condition=excluded.student_condition,
             damage_description=excluded.damage_description,missing_items=excluded.missing_items,
             photo_references=excluded.photo_references,verification_status='return_submitted',
             verified_at=NULL,verified_by=NULL,actual_returned_at=NULL,staff_condition='',staff_notes='',verification_photos='[]'""",
        (data["requestId"], data["submittedBy"], data["claimedReturnedAt"], data["studentCondition"],
         data["damageDescription"], data["missingItems"], json.dumps(data["photoReferences"])),
    )
    db._audit(data["submittedBy"], "request", data["requestId"], "return_submitted", data)
    db._emit("return.submitted", "request", data["requestId"], data)
    db.connection.commit()
    return return_submission_view(data["requestId"])


def verify_return_submission(data: dict):
    """Apply a staff decision and finalize verified returns when appropriate."""
    valid = {"verified_returned", "verified_damaged", "missing_items", "disputed_return"}
    status = data.get("verificationStatus")
    if status not in valid:
        raise ApiError("Invalid verificationStatus")
    submission = return_submission_view(data["requestId"])
    if not submission:
        raise ApiError("No return submission exists", 404)
    actual = data.get("actualReturnedAt") or submission["claimed_returned_at"]
    iso_date(actual, "actualReturnedAt")
    photos = data.get("verificationPhotos", [])
    if not isinstance(photos, list):
        raise ApiError("verificationPhotos must be a list")
    db.connection.execute(
        """UPDATE return_submissions SET verification_status=?,verified_at=CURRENT_TIMESTAMP,
           verified_by=?,actual_returned_at=?,staff_condition=?,staff_notes=?,verification_photos=?
           WHERE request_id=?""",
        (status, data["verifiedBy"], actual, data.get("staffCondition", ""),
         data.get("staffNotes", ""), json.dumps(photos), data["requestId"]),
    )
    if status in {"verified_returned", "verified_damaged", "missing_items"}:
        db.record_return({
            "requestId": data["requestId"],
            "actorId": data["verifiedBy"],
            "returnedAt": actual,
            "condition": data.get("staffCondition") or submission["student_condition"],
            "damageFlag": status in {"verified_damaged", "missing_items"},
            "notes": data.get("staffNotes", "") or submission["damage_description"],
        })
    db._audit(data["verifiedBy"], "request", data["requestId"], "return_verified", data)
    db._emit("return.verified", "request", data["requestId"], data)
    db.connection.commit()
    return return_submission_view(data["requestId"])


def request_owner(request_id: int):
    """Load a request or raise a not-found API error."""
    request = request_view(request_id)
    if not request:
        raise ApiError("Request not found", 404)
    return request


def request_list(filters: dict):
    """List requests using optional requester and status filters."""
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
    """Reject unavailable equipment and any interval overlap."""
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


equipment_service = EquipmentService(db)
notification_service = NotificationService(db)
request_service = RequestService(db, request_list, ensure_available)
authentication_service = AuthenticationService(
    db, ApiError, SESSION_COOKIE, COOKIE_SECURE, SESSION_SECONDS,
    STAFF_ROLES, ADMIN_EMAILS, ROLE_BY_EMAIL_DOMAIN, STAFF_EMAIL_DOMAINS,
)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "MediaLabManager/1.0"

    def log_message(self, fmt, *args):
        """Write one HTTP request to the server log."""
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, status: int, value, headers: dict | None = None):
        """Send a JSON response with optional headers."""
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
        """Convert an exception into a JSON API error response."""
        status = error.status if isinstance(error, ApiError) else 500
        self.send_json(status, {"error": str(error)})

    def cookies(self):
        """Parse cookies from the incoming request."""
        values = {}
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                values[key] = value
        return values

    def current_user(self):
        """Resolve and refresh the current database-backed session."""
        return authentication_service.current_user(self)

    def require_user(self):
        """Require an authenticated user for the current request."""
        user = self.current_user()
        if not user:
            raise ApiError("You must sign in first", 401)
        return user

    def require_staff(self):
        """Require an authenticated staff user."""
        user = self.require_user()
        if not authentication_service.is_staff(user):
            raise ApiError("Staff access is required", 403)
        return user

    def require_admin(self):
        """Require an authenticated administrator."""
        user = self.require_user()
        if not authentication_service.is_admin(user):
            raise ApiError("Administrator access is required", 403)
        return user

    def read_body(self):
        """Read and decode a bounded JSON request body."""
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
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-MLM-CSRF")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, OPTIONS")
        self.end_headers()

    def do_GET(self):
        """Route GET requests to the API or static-file handler."""
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.route("GET", parsed.path, parse_qs(parsed.query))
            else:
                self.static_file(parsed.path)
        except Exception as error:
            self.fail(error)

    def do_POST(self):
        """Route POST requests to the API."""
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                raise ApiError("Route not found", 404)
            self.route("POST", parsed.path, self.read_body())
        except Exception as error:
            self.fail(error)

    def do_PATCH(self):
        """Route PATCH requests to the API."""
        try:
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                raise ApiError("Route not found", 404)
            self.route("PATCH", parsed.path, self.read_body())
        except Exception as error:
            self.fail(error)

    def do_PUT(self):
        """Treat PUT requests as PATCH requests."""
        self.do_PATCH()

    def route(self, method, path, data):
        """Dispatch an API request to authentication or workflow logic."""
        if method == "POST" and path == "/api/auth/login":
            return authentication_service.login(self, data, check_login_allowed, record_failed_login, clear_failed_logins)
        if method == "POST" and path == "/api/auth/logout":
            if self.headers.get("X-MLM-CSRF") != "1":
                raise ApiError("CSRF check failed", 403)
            token = self.cookies().get(SESSION_COOKIE)
            if token:
                db.connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
                db.connection.commit()
            return self.send_json(200, {"ok": True, "clearClientCart": True}, {"Set-Cookie": cookie_header("", 0)})
        if method == "GET" and path == "/api/auth/me":
            user = self.require_user()
            return self.send_json(200, {"user": user})

        if method == "POST" and self.headers.get("X-MLM-CSRF") != "1":
            raise ApiError("CSRF check failed", 403)
        user = self.require_user()
        if method == "GET" and path == "/api/equipment":
            filters = {key: values[0] for key, values in data.items()}
            return self.send_json(200, equipment_service.list_units(filters))
        if method == "GET" and path == "/api/listings":
            filters = {key: values[0] for key, values in data.items()}
            return self.send_json(200, equipment_service.list_catalog(filters))
        if method == "GET" and path == "/api/policy":
            settings = db.get_settings()
            return self.send_json(200, {"standardLoanHours": settings.get("standardLoanHours", settings.get("standard_loan_hours", 72))})
        if method == "GET" and path == "/api/equipment/stats":
            self.require_staff()
            return self.send_json(200, equipment_service.stats())
        if method == "GET" and path == "/api/damage-reports":
            self.require_staff()
            filters = {key: values[0] for key, values in data.items()}
            return self.send_json(200, equipment_service.list_damage_reports(filters))
        if method == "POST" and path == "/api/equipment":
            self.require_staff()
            return self.send_json(201, equipment_service.add_unit(data))
        if method in {"PATCH", "PUT"} and len(path.split("/")) == 4 and path.split("/")[2] == "equipment":
            self.require_staff()
            return self.send_json(200, equipment_service.update_unit(int(path.split("/")[3]), data, user["id"]))
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
            return self.send_json(201, request_service.create(body))
        if method == "GET" and path == "/api/requests":
            filters = {key: values[0] for key, values in data.items()}
            staff_access = is_staff(user)
            if not staff_access:
                filters["requesterId"] = str(user["id"])
            elif filters.get("requesterId"):
                filters["requesterId"] = str(int(filters["requesterId"]))
            return self.send_json(200, request_service.list(filters))

        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) >= 4 and parts[1] == "requests":
            request_id = int(parts[2])
            request = request_owner(request_id)
            action = parts[3]
            staff_access = is_staff(user)
            if action == "return-submission":
                if request["requester_id"] != user["id"] and not staff_access:
                    raise ApiError("You do not own this request", 403)
                if method == "GET":
                    return self.send_json(200, return_submission_view(request_id))
                if method == "POST":
                    return self.send_json(202, create_return_submission(return_payload(data, request_id, user["id"])))
                raise ApiError("Method not allowed", 405)
            if action == "return-verification":
                if method != "POST":
                    raise ApiError("Method not allowed", 405)
                self.require_staff()
                verification = {**data, "requestId": request_id, "verifiedBy": user["id"]}
                return self.send_json(200, verify_return_submission(verification))
            if action == "pickup-slot":
                if method != "POST":
                    raise ApiError("Method not allowed", 405)
                self.require_staff()
                validate_pickup_slot(request_id, data.get("startsAt"), data.get("endsAt"))
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(201, request_service.assign_pickup_slot(body))
            if action == "pickup-response":
                if method != "POST":
                    raise ApiError("Method not allowed", 405)
                if request["requester_id"] != user["id"]:
                    raise ApiError("You do not own this request", 403)
                status = data.get("status")
                if status not in {"accepted", "rejected"}:
                    raise ApiError("status must be accepted or rejected")
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(200, request_service.respond_pickup_slot(body))
            if action == "cancel":
                if request["requester_id"] != user["id"] and not staff_access:
                    raise ApiError("You do not own this request", 403)
                return self.send_json(200, request_service.cancel(request_id, user["id"]))
            if action in {"approve", "reject", "windows", "pickup"} and not staff_access:
                raise ApiError("Staff access is required", 403)
            if action == "approve":
                return self.send_json(200, request_service.approve(request_id, user["id"], data.get("notes", "")))
            if action == "reject":
                return self.send_json(200, request_service.reject(request_id, user["id"], data.get("reason", "")))
            if action == "windows":
                starts_at = iso_date(data.get("startsAt"), "startsAt")
                ends_at = iso_date(data.get("endsAt"), "endsAt")
                if ends_at <= starts_at:
                    raise ApiError("endsAt must be after startsAt")
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(201, request_service.schedule_window(body))
            if action == "extensions":
                if request["requester_id"] != user["id"] and not staff_access:
                    raise ApiError("You do not own this request", 403)
                starts_at = iso_date(data.get("startsAt"), "startsAt")
                ends_at = iso_date(data.get("endsAt"), "endsAt")
                if ends_at <= starts_at:
                    raise ApiError("endsAt must be after startsAt")
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(201, request_service.request_extension(body))
            if action == "pickup":
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(200, request_service.pickup(body))
            if action == "return":
                if request["requester_id"] != user["id"] and not staff_access:
                    raise ApiError("You do not own this request", 403)
                if method == "POST" and not staff_access:
                    return self.send_json(202, create_return_submission(return_payload(data, request_id, user["id"])))
                body = {**data, "requestId": request_id, "actorId": user["id"]}
                return self.send_json(200, request_service.return_equipment(body))
        if len(parts) == 4 and parts[1] == "request-items" and parts[3] == "damage":
            self.require_staff()
            body = {**data, "requestItemId": int(parts[2]), "reportedBy": user["id"]}
            if not body.get("description"):
                raise ApiError("description is required")
            return self.send_json(201, request_service.damage(body))
        if method == "GET" and len(parts) == 4 and parts[1] == "audit":
            self.require_staff()
            return self.send_json(200, notification_service.audit_history(parts[2], int(parts[3])))
        if method == "GET" and path == "/api/dashboard":
            self.require_staff()
            return self.send_json(200, notification_service.dashboard())
        if method == "GET" and path == "/api/outbox":
            self.require_staff()
            return self.send_json(200, notification_service.pending_events())
        raise ApiError("API route not found", 404)

    def login(self, data):
        """Validate credentials and create a database-backed session."""
        return authentication_service.login(self, data, check_login_allowed, record_failed_login, clear_failed_logins)

    def static_file(self, path):
        """Serve frontend files while protecting application pages."""
        path = "/index.html" if path in {"", "/"} else path
        user = self.current_user()
        if path.startswith("/pages/admin/"):
            if not user or not is_admin(user):
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
    """Start the HTTP server and close resources on shutdown."""
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
