"""Add a comprehensive, repeatable example dataset for local testing.

Run from the repository root with:
    python MLM.Database/seed_test_equipment.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mlm_database_commands import Database


DB_PATH = Path(os.environ.get("MEDIA_LAB_DB", Path(__file__).with_name("media-lab.sqlite")))

USERS = [
    ("student.alex", "Alex Morgan", "alex.morgan@krea.ac.in", "Film", "student", "2468"),
    ("student.priya", "Priya Shah", "priya.shah@krea.ac.in", "Communication", "student", "1357"),
    ("staff.maya", "Maya Chen", "maya.chen@krea.edu.in", "Media Lab", "media_lab", "8642"),
    ("admin.demo", "Demo Administrator", "demo.admin@krea.edu.in", "Media Lab", "admin", "9999"),
]

LISTINGS = [
    ("CAM-FX3", "Sony FX3 Cinema Camera", "Full-frame cinema camera body.", "Cameras", "Camera Cage", 2),
    ("CAM-R6", "Canon EOS R6 Mark II", "Full-frame mirrorless camera body.", "Cameras", "Camera Cage", 2),
    ("LENS-2470", "Sigma 24-70mm f/2.8 DG DN", "Standard zoom lens.", "Lenses", "Lens Cabinet", 3),
    ("AUDIO-RODE", "RØDE Wireless GO II Kit", "Two-channel wireless microphone kit.", "Audio", "Audio Shelf", 2),
    ("AUDIO-ZOOM", "Zoom H6 Field Recorder", "Portable multitrack audio recorder.", "Audio", "Audio Shelf", 2),
    ("LIGHT-120D", "Aputure 120d II LED Light", "Continuous LED light.", "Lighting", "Lighting Bay", 2),
    ("LIGHT-BULB", "E27 LED Lightbulb", "Identical bulbs tracked individually for damage assessment.", "Lighting", "Lighting Bay", 5),
    ("GRIP-TRIPOD", "Manfrotto Video Tripod", "Fluid-head video tripod.", "Accessories", "Grip Room", 3),
    ("GRIP-RS3", "DJI RS 3 Gimbal", "Camera stabilizer with accessories.", "Accessories", "Grip Room", 2),
    ("DISPLAY-NINJA", "Atomos Ninja V Monitor", "On-camera monitor.", "Accessories", "Service Desk", 1),
]


# Image attribution: these are sample placeholder images served by placehold.co.
# Replace them with approved lab photographs and retain the source/credit metadata.
IMAGES = {
    "CAM-FX3": [{"url": "https://placehold.co/800x500/png?text=Sony+FX3", "alt": "Sony FX3 cinema camera", "attribution": "Placeholder image: placehold.co"}],
    "CAM-R6": [{"url": "https://placehold.co/800x500/png?text=Canon+R6", "alt": "Canon EOS R6 Mark II", "attribution": "Placeholder image: placehold.co"}],
    "LENS-2470": [{"url": "https://placehold.co/800x500/png?text=Sigma+24-70mm", "alt": "Sigma 24-70mm zoom lens", "attribution": "Placeholder image: placehold.co"}],
    "AUDIO-RODE": [{"url": "https://placehold.co/800x500/png?text=Wireless+GO+II", "alt": "RØDE Wireless GO II kit", "attribution": "Placeholder image: placehold.co"}],
    "AUDIO-ZOOM": [{"url": "https://placehold.co/800x500/png?text=Zoom+H6", "alt": "Zoom H6 field recorder", "attribution": "Placeholder image: placehold.co"}],
    "LIGHT-120D": [{"url": "https://placehold.co/800x500/png?text=Aputure+120d", "alt": "Aputure 120d II LED light", "attribution": "Placeholder image: placehold.co"}],
    "LIGHT-BULB": [{"url": "https://placehold.co/800x500/png?text=LED+Bulb", "alt": "E27 LED lightbulb", "attribution": "Placeholder image: placehold.co"}],
    "GRIP-TRIPOD": [{"url": "https://placehold.co/800x500/png?text=Video+Tripod", "alt": "Manfrotto video tripod", "attribution": "Placeholder image: placehold.co"}],
    "GRIP-RS3": [{"url": "https://placehold.co/800x500/png?text=DJI+RS+3", "alt": "DJI RS 3 gimbal", "attribution": "Placeholder image: placehold.co"}],
    "DISPLAY-NINJA": [{"url": "https://placehold.co/800x500/png?text=Atomos+Ninja+V", "alt": "Atomos Ninja V monitor", "attribution": "Placeholder image: placehold.co"}],
}

def pin_hash(pin: str) -> str:
    salt = hashlib.sha256(("example-salt-" + pin).encode()).digest()[:16]
    value = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$%s$%s" % (salt.hex(), value.hex())


def main() -> None:
    database = Database(DB_PATH)
    connection = database.connection

    for krea_id, name, email, department, role, pin in USERS:
        connection.execute(
            """INSERT INTO users (krea_id,name,email,department,role,pin_hash)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(krea_id) DO UPDATE SET
                 name=excluded.name,
                 email=excluded.email,
                 department=excluded.department,
                 role=excluded.role,
                 pin_hash=excluded.pin_hash,
                 banned=0,
                 updated_at=CURRENT_TIMESTAMP""",
            (krea_id, name, email, department, role, pin_hash(pin)),
        )

    connection.executemany(
        "INSERT OR IGNORE INTO lab_settings(setting_key,setting_value) VALUES (?,?)",
        [("standard_loan_hours", "72"), ("return_reminder_hours", "24"), ("staff_notifications", "true")],
    )

    listing_ids = {}
    for code, name, description, category, location, quantity in LISTINGS:
        connection.execute(
            """INSERT OR IGNORE INTO listings
               (listing_code,name,description,category,location,quantity,images)
               VALUES (?,?,?,?,?,?,?)""",
            (code, name, description, category, location, quantity, json.dumps(IMAGES[code])),
        )
        connection.execute("UPDATE listings SET images=? WHERE listing_code=? AND (images IS NULL OR images IN ('[]','{}'))", (json.dumps(IMAGES[code]), code))
        listing_ids[code] = connection.execute(
            "SELECT id FROM listings WHERE listing_code=?", (code,)
        ).fetchone()["id"]

    for code, name, description, category, location, quantity in LISTINGS:
        status = "maintenance" if code == "DISPLAY-NINJA" else "available"
        for number in range(1, quantity + 1):
            connection.execute(
                """INSERT OR IGNORE INTO equipment
                   (listing_id,asset_code,name,description,serial_number,status,location)
                   VALUES (?,?,?,?,?,?,?)""",
                (listing_ids[code], f"{code}-{number:03d}", name, description,
                 f"SERIAL-{code}-{number:03d}", status, location),
            )
    connection.commit()

    user_ids = {
        row["krea_id"]: row["id"]
        for row in connection.execute("SELECT id,krea_id FROM users")
    }
    equipment_ids = {
        row["asset_code"]: row["id"]
        for row in connection.execute("SELECT id,asset_code FROM equipment")
    }

    if not connection.execute(
        "SELECT id FROM requests WHERE purpose='Example pending booking'"
    ).fetchone():
        database.create_request({
            "requesterId": user_ids["student.alex"],
            "equipmentIds": [equipment_ids["CAM-FX3-001"]],
            "purpose": "Example pending booking",
            "academicPriority": 1,
            "pickupStartsAt": "2026-10-05T10:00:00Z",
            "pickupEndsAt": "2026-10-05T11:00:00Z",
            "returnStartsAt": "2026-10-07T10:00:00Z",
            "returnEndsAt": "2026-10-07T11:00:00Z",
        })

    if not connection.execute(
        "SELECT id FROM requests WHERE purpose='Example active loan'"
    ).fetchone():
        request = database.create_request({
            "requesterId": user_ids["student.priya"],
            "equipmentIds": [equipment_ids["LENS-2470-001"]],
            "purpose": "Example active loan",
            "pickupStartsAt": "2026-09-28T10:00:00Z",
            "pickupEndsAt": "2026-09-28T11:00:00Z",
            "returnStartsAt": "2026-10-01T10:00:00Z",
            "returnEndsAt": "2026-10-01T11:00:00Z",
        })
        database.approve_request(request["id"], user_ids["staff.maya"])
        database.record_pickup({"requestId": request["id"], "actorId": user_ids["staff.maya"]})

    if not connection.execute(
        "SELECT id FROM requests WHERE purpose='Example damaged bulb return'"
    ).fetchone():
        request = database.create_request({
            "requesterId": user_ids["student.alex"],
            "equipmentIds": [equipment_ids["LIGHT-BULB-001"]],
            "purpose": "Example damaged bulb return",
            "pickupStartsAt": "2026-09-20T10:00:00Z",
            "pickupEndsAt": "2026-09-20T11:00:00Z",
            "returnStartsAt": "2026-09-22T10:00:00Z",
            "returnEndsAt": "2026-09-22T11:00:00Z",
        })
        database.approve_request(request["id"], user_ids["staff.maya"])
        database.record_pickup({"requestId": request["id"], "actorId": user_ids["staff.maya"]})
        database.record_return({
            "requestId": request["id"],
            "actorId": user_ids["staff.maya"],
            "condition": "Cracked housing",
            "damageFlag": True,
            "notes": "One bulb damaged; remaining identical bulbs stay available.",
        })

    database.close()
    print(f"Example data available in {DB_PATH}")
    print(f"Users: {len(USERS)} | Listings: {len(LISTINGS)} | Equipment units: {len(equipment_ids)}")
    print("Example PINs: Alex 2468, Priya 1357, Maya 8642, Admin 9999")


if __name__ == "__main__":
    main()
