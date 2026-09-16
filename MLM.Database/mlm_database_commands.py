"""SQLite persistence and workflow commands for Media Lab Manager.

The public functions mirror the original JavaScript database module. Records
are returned as plain dictionaries; collections are returned as lists.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DB_PATH = Path(os.environ.get("MEDIA_LAB_DB", Path(__file__).with_name("media-lab.sqlite")))


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, krea_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  email TEXT UNIQUE, department TEXT DEFAULT '', role TEXT DEFAULT 'student',
  notification_preferences TEXT DEFAULT '{}', banned INTEGER DEFAULT 0,
  pin_hash TEXT DEFAULT '', failed_pin_attempts INTEGER DEFAULT 0,
  locked_until TEXT,
  ban_reason TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_attempts (
  id INTEGER PRIMARY KEY, ip_address TEXT NOT NULL, email TEXT NOT NULL,
  failed_attempts INTEGER DEFAULT 0, window_started_at TEXT NOT NULL,
  locked_until TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ip_address, email)
);
CREATE TABLE IF NOT EXISTS lab_settings (
  setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value or {}, separators=(",", ":"))


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _one(value: Any) -> Any:
    return value[0] if isinstance(value, dict) and len(value) == 1 else value


class Database:
    """Database facade. Create one instance per backend process or database path."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path or DB_PATH)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(SCHEMA)
        for statement in (
            "ALTER TABLE users ADD COLUMN pin_hash TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN failed_pin_attempts INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN locked_until TEXT",
        ):
            try:
                self.connection.execute(statement)
            except sqlite3.OperationalError as error:
                if "duplicate column name" not in str(error).lower():
                    raise
        self.connection.execute("UPDATE users SET role='student' WHERE role='lendee' OR role IS NULL OR role='' ")
        self.connection.commit()

    @contextmanager
    def _transaction(self):
        try:
            yield
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _audit(self, actor: int | None, entity_type: str, entity_id: int, action: str, details: Any = None):
        self.connection.execute(
            "INSERT INTO audit_log(actor_id,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
            (actor or None, entity_type, entity_id, action, _json(details)),
        )

    def _emit(self, event_type: str, aggregate_type: str, aggregate_id: int, payload: Any = None):
        self.connection.execute(
            "INSERT INTO outbox_events(event_type,aggregate_type,aggregate_id,payload) VALUES (?,?,?,?)",
            (event_type, aggregate_type, aggregate_id, _json(payload)),
        )

    def add_user(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("kreaId") or not data.get("name"):
            raise ValueError("kreaId and name are required")
        cur = self.connection.execute(
            "INSERT INTO users(krea_id,name,email,department,role,notification_preferences) VALUES (?,?,?,?,?,?)",
            (data["kreaId"], data["name"], data.get("email"), data.get("department", ""),
             data.get("role", "student"), _json(data.get("notificationPreferences"))),
        )
        self.connection.commit()
        return _row(self.connection.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())

    def list_users(self):
        return _rows(self.connection.execute(
            "SELECT id,krea_id,name,email,department,role,banned,created_at FROM users ORDER BY name COLLATE NOCASE"
        ))

    def update_user(self, user_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        fields = {"kreaId": "krea_id", "name": "name", "email": "email", "department": "department",
                  "role": "role", "banned": "banned", "banReason": "ban_reason"}
        updates = [(column, data[key]) for key, column in fields.items() if key in data]
        if updates:
            assignments = ",".join(f"{column}=?" for column, _ in updates)
            self.connection.execute(f"UPDATE users SET {assignments},updated_at=? WHERE id=?",
                                    [value for _, value in updates] + [_now(), user_id])
            self.connection.commit()
        return _row(self.connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

    def ban_user(self, user_id: int, reason: str = "", actor_id: int | None = None):
        with self._transaction():
            self.update_user(user_id, {"banned": 1, "banReason": reason})
            self.connection.execute("INSERT INTO ban_history(user_id,action,reason,actor_id) VALUES (?,?,?,?)",
                                    (user_id, "banned", reason, actor_id))
            self._audit(actor_id, "user", user_id, "banned", {"reason": reason})
            self._emit("user.banned", "user", user_id, {"reason": reason})
        return self.update_user(user_id, {})

    def unban_user(self, user_id: int, actor_id: int | None = None):
        with self._transaction():
            self.update_user(user_id, {"banned": 0, "banReason": ""})
            self.connection.execute("INSERT INTO ban_history(user_id,action,actor_id) VALUES (?,?,?)",
                                    (user_id, "unbanned", actor_id))
            self._audit(actor_id, "user", user_id, "unbanned")
            self._emit("user.unbanned", "user", user_id)
        return self.update_user(user_id, {})

    def add_equipment(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("name"):
            raise ValueError("name is required")
        asset_code = data.get("assetCode") or f"ASSET-{int(datetime.now().timestamp() * 1000)}"
        cur = self.connection.execute(
            "INSERT INTO equipment(asset_code,name,description,serial_number,status,location) VALUES (?,?,?,?,?,?)",
            (asset_code, data["name"], data.get("description", ""), data.get("serialNumber"),
             data.get("status", "available"), data.get("location", "")),
        )
        self.connection.commit()
        return _row(self.connection.execute("SELECT * FROM equipment WHERE id=?", (cur.lastrowid,)).fetchone())

    def get_settings(self) -> dict[str, Any]:
        return {row["setting_key"]: row["setting_value"] for row in self.connection.execute("SELECT setting_key,setting_value FROM lab_settings ORDER BY setting_key")}

    def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        allowed = {"standardLoanHours", "returnReminderHours", "notifyStaff", "notifyStudents"}
        for key, value in data.items():
            if key in allowed:
                self.connection.execute(
                    "INSERT INTO lab_settings(setting_key,setting_value,updated_at) VALUES (?,?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_at=excluded.updated_at",
                    (key, json.dumps(value), _now()),
                )
        self.connection.commit()
        return self.get_settings()

    def update_equipment(self, equipment_id: int, data: dict[str, Any], actor_id: int | None = None):
        fields = {"assetCode": "asset_code", "name": "name", "description": "description",
                  "serialNumber": "serial_number", "status": "status", "location": "location"}
        updates = [(column, data[key]) for key, column in fields.items() if key in data]
        if updates:
            assignments = ",".join(f"{column}=?" for column, _ in updates)
            self.connection.execute(f"UPDATE equipment SET {assignments},updated_at=? WHERE id=?",
                                    [value for _, value in updates] + [_now(), equipment_id])
        self._audit(actor_id, "equipment", equipment_id, "updated", data)
        self.connection.commit()
        return _row(self.connection.execute("SELECT * FROM equipment WHERE id=?", (equipment_id,)).fetchone())

    def check_availability(self, equipment_ids: int | list[int], starts_at: str, ends_at: str) -> list[int]:
        ids = equipment_ids if isinstance(equipment_ids, list) else [equipment_ids]
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        query = f"""SELECT DISTINCT ri.equipment_id FROM request_items ri
          JOIN requests r ON r.id=ri.request_id JOIN time_windows w ON w.request_id=r.id
          WHERE ri.equipment_id IN ({marks})
            AND r.status IN ('pending','approved','pickup_pending','picked_up','overdue')
            AND w.status IN ('requested','approved') AND w.starts_at < ? AND w.ends_at > ?"""
        return [row["equipment_id"] for row in self.connection.execute(query, [*ids, starts_at, ends_at])]

    def _request_view(self, request_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT r.*,u.krea_id,u.name AS requester_name,u.email AS requester_email "
            "FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.id=?", (request_id,)
        ).fetchone()
        result = _row(row)
        if result is None:
            return None
        result["items"] = _rows(self.connection.execute(
            "SELECT ri.*,e.asset_code,e.name,e.status AS equipment_status FROM request_items ri "
            "JOIN equipment e ON e.id=ri.equipment_id WHERE ri.request_id=?", (request_id,)
        ))
        result["windows"] = _rows(self.connection.execute(
            "SELECT * FROM time_windows WHERE request_id=? ORDER BY starts_at", (request_id,)
        ))
        return result

    def create_request(self, data: dict[str, Any]) -> dict[str, Any] | None:
        ids = [item.get("id", item) if isinstance(item, dict) else item for item in data.get("equipmentIds", data.get("items", []))]
        if not data.get("requesterId") or not ids:
            raise ValueError("requesterId and equipmentIds are required")
        with self._transaction():
            user = self.connection.execute("SELECT * FROM users WHERE id=?", (data["requesterId"],)).fetchone()
            if user is None:
                raise ValueError("user not found")
            if user["banned"]:
                raise ValueError("user is banned")
            conflicts = self.check_availability(ids, data.get("pickupStartsAt"), data.get("returnEndsAt"))
            if conflicts:
                raise ValueError("equipment unavailable: " + ",".join(map(str, conflicts)))
            cur = self.connection.execute(
                "INSERT INTO requests(requester_id,purpose,academic_priority) VALUES (?,?,?)",
                (data["requesterId"], data.get("purpose", ""), data.get("academicPriority", 0)),
            )
            request_id = cur.lastrowid
            for equipment_id in ids:
                self.connection.execute("INSERT INTO request_items(request_id,equipment_id) VALUES (?,?)", (request_id, equipment_id))
                self.connection.execute("UPDATE equipment SET status='requested',updated_at=? WHERE id=?", (_now(), equipment_id))
            for kind, start_key, end_key in (("pickup", "pickupStartsAt", "pickupEndsAt"), ("return", "returnStartsAt", "returnEndsAt")):
                if data.get(start_key) and data.get(end_key):
                    self.connection.execute("INSERT INTO time_windows(request_id,kind,starts_at,ends_at) VALUES (?,?,?,?)",
                                            (request_id, kind, data[start_key], data[end_key]))
            self._audit(data["requesterId"], "request", request_id, "created", {"equipmentIds": ids})
            self._emit("request.created", "request", request_id, {"equipmentIds": ids})
        return self._request_view(request_id)

    def set_request_status(self, request_id: int, status: str, actor_id: int | None = None, details: dict[str, Any] | None = None):
        details = details or {}
        with self._transaction():
            request = self.connection.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if request is None:
                raise ValueError("request not found")
            self.connection.execute(
                "UPDATE requests SET status=?,rejection_reason=?,approval_notes=?,updated_at=? WHERE id=?",
                (status, details.get("reason", request["rejection_reason"]), details.get("notes", request["approval_notes"]), _now(), request_id),
            )
            self.connection.execute("UPDATE request_items SET status=? WHERE request_id=?", (status, request_id))
            if status == "approved":
                self.connection.execute("UPDATE equipment SET status='pickup_pending',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", (_now(), request_id))
            elif status in ("rejected", "cancelled"):
                self.connection.execute("UPDATE equipment SET status='available',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", (_now(), request_id))
            self._audit(actor_id, "request", request_id, status, details)
            self._emit(f"request.{status}", "request", request_id, details)
        return self._request_view(request_id)

    def approve_request(self, request_id, actor_id, notes=""): return self.set_request_status(request_id, "approved", actor_id, {"notes": notes})
    def reject_request(self, request_id, actor_id, reason=""): return self.set_request_status(request_id, "rejected", actor_id, {"reason": reason})
    def cancel_request(self, request_id, actor_id): return self.set_request_status(request_id, "cancelled", actor_id)

    def schedule_window(self, data):
        cur = self.connection.execute(
            "INSERT INTO time_windows(request_id,kind,starts_at,ends_at,status,notes) VALUES (?,?,?,?,?,?)",
            (data["requestId"], data.get("kind", "pickup"), data["startsAt"], data["endsAt"], data.get("status", "requested"), data.get("notes", "")),
        )
        self._audit(data.get("actorId"), "request", data["requestId"], "window_scheduled", data)
        self._emit("window.updated", "request", data["requestId"], data)
        self.connection.commit()
        return _row(self.connection.execute("SELECT * FROM time_windows WHERE id=?", (cur.lastrowid,)).fetchone())

    def request_extension(self, data):
        return self.schedule_window({**data, "kind": "extension", "status": "requested"})

    def record_pickup(self, data):
        with self._transaction():
            ids = data.get("requestItemIds") or [row["id"] for row in self.connection.execute("SELECT id FROM request_items WHERE request_id=?", (data["requestId"],))]
            for item_id in ids:
                self.connection.execute("INSERT INTO returns(request_item_id,picked_up_at) VALUES (?,?) ON CONFLICT(request_item_id) DO UPDATE SET picked_up_at=excluded.picked_up_at", (item_id, data.get("pickedUpAt", _now())))
                self.connection.execute("UPDATE request_items SET status='picked_up' WHERE id=?", (item_id,))
            self.connection.execute("UPDATE requests SET status='picked_up',updated_at=? WHERE id=?", (_now(), data["requestId"]))
            self.connection.execute("UPDATE equipment SET status='picked_up',updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", (_now(), data["requestId"]))
            self._audit(data.get("actorId"), "request", data["requestId"], "pickup_confirmed", data)
            self._emit("pickup.confirmed", "request", data["requestId"], data)
        return self._request_view(data["requestId"])

    def mark_no_show(self, request_id, actor_id):
        self.connection.execute("UPDATE returns SET no_show=1 WHERE request_item_id IN (SELECT id FROM request_items WHERE request_id=?)", (request_id,))
        self.cancel_request(request_id, actor_id)
        self._emit("pickup.no_show", "request", request_id)
        self.connection.commit()
        return self._request_view(request_id)

    def record_return(self, data):
        with self._transaction():
            ids = data.get("requestItemIds") or [row["id"] for row in self.connection.execute("SELECT id FROM request_items WHERE request_id=?", (data["requestId"],))]
            for item_id in ids:
                self.connection.execute("INSERT INTO returns(request_item_id,returned_at,returned_flag,condition,damage_flag,notes) VALUES (?,?,1,?,?,?) ON CONFLICT(request_item_id) DO UPDATE SET returned_at=excluded.returned_at,returned_flag=1,condition=excluded.condition,damage_flag=excluded.damage_flag,notes=excluded.notes", (item_id, data.get("returnedAt", _now()), data.get("condition", ""), int(bool(data.get("damageFlag"))), data.get("notes", "")))
                self.connection.execute("UPDATE request_items SET status=? WHERE id=?", ("damaged" if data.get("damageFlag") else "returned", item_id))
            self.connection.execute("UPDATE requests SET status='returned',updated_at=? WHERE id=?", (_now(), data["requestId"]))
            self.connection.execute("UPDATE equipment SET status=?,updated_at=? WHERE id IN (SELECT equipment_id FROM request_items WHERE request_id=?)", ("damaged" if data.get("damageFlag") else "available", _now(), data["requestId"]))
            self._audit(data.get("actorId"), "request", data["requestId"], "return_recorded", data)
            self._emit("return.recorded", "request", data["requestId"], data)
        return self._request_view(data["requestId"])

    def record_damage(self, data):
        cur = self.connection.execute("INSERT INTO damage_reports(request_item_id,reported_by,description,severity) VALUES (?,?,?,?)", (data["requestItemId"], data.get("reportedBy"), data["description"], data.get("severity", "unknown")))
        self.connection.execute("UPDATE request_items SET status='damaged' WHERE id=?", (data["requestItemId"],))
        self._audit(data.get("reportedBy"), "request_item", data["requestItemId"], "damage_reported", data)
        self._emit("damage.reported", "request_item", data["requestItemId"], data)
        self.connection.commit()
        return _row(self.connection.execute("SELECT * FROM damage_reports WHERE id=?", (cur.lastrowid,)).fetchone())

    def get_dashboard(self):
        return {
            "pendingRequests": _rows(self.connection.execute("SELECT r.*,u.name AS requester_name FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.status='pending' ORDER BY r.academic_priority DESC,r.created_at")),
            "windows": _rows(self.connection.execute("SELECT w.*,r.status,u.name AS requester_name FROM time_windows w JOIN requests r ON r.id=w.request_id JOIN users u ON u.id=r.requester_id ORDER BY w.starts_at")),
            "equipment": _rows(self.connection.execute("SELECT * FROM equipment ORDER BY name COLLATE NOCASE")),
        }

    def get_audit_history(self, entity_type, entity_id):
        return _rows(self.connection.execute("SELECT * FROM audit_log WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC", (entity_type, entity_id)))

    def get_outbox(self, limit=100):
        limit = min(max(int(limit or 100), 1), 1000)
        return _rows(self.connection.execute("SELECT * FROM outbox_events WHERE published_at IS NULL ORDER BY id LIMIT ?", (limit,)))

    def mark_events_published(self, ids):
        with self._transaction():
            self.connection.executemany("UPDATE outbox_events SET published_at=? WHERE id=?", [(_now(), event_id) for event_id in ids])

    def find(self, filters=None):
        filters = filters or {}
        clauses, params = [], []
        if filters.get("status"):
            clauses.append("status=?")
            params.append(filters["status"])
        if filters.get("q"):
            clauses.append("(name LIKE ? OR asset_code LIKE ? OR serial_number LIKE ? OR description LIKE ?)")
            params.extend([f"%{filters['q']}%"] * 4)
        limit = min(max(int(filters.get("limit", 100)), 1), 1000)
        offset = max(int(filters.get("offset", 0)), 0)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return _rows(self.connection.execute(f"SELECT * FROM equipment{where} ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?", [*params, limit, offset]))

    def stats(self):
        return _rows(self.connection.execute("SELECT status,COUNT(*) AS count FROM equipment GROUP BY status ORDER BY status"))

    def close(self):
        self.connection.close()


db = Database()


def close():
    """Close the module-level database connection."""
    db.close()
