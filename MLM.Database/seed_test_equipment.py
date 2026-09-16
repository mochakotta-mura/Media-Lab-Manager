"""Insert a small idempotent equipment set for local frontend testing."""
from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).with_name("media-lab.sqlite")
EQUIPMENT = [
    ("TEST-CAM-001", "Sony FX3 Cinema Camera", "Placeholder camera for catalog and booking tests.", "TEST-SN-FX3-001", "available", "Camera Cage"),
    ("TEST-CAM-002", "Canon EOS R6 Mark II", "Placeholder mirrorless camera for catalog and booking tests.", "TEST-SN-R6-002", "available", "Camera Cage"),
    ("TEST-LENS-001", "Sigma 24-70mm f/2.8 DG DN", "Placeholder standard zoom lens.", "TEST-SN-SIGMA-001", "available", "Lens Cabinet"),
    ("TEST-AUD-001", "RØDE Wireless GO II Kit", "Placeholder wireless microphone kit.", "TEST-SN-RODE-001", "available", "Audio Shelf"),
    ("TEST-AUD-002", "Zoom H6 Field Recorder", "Placeholder portable audio recorder.", "TEST-SN-ZOOM-002", "available", "Audio Shelf"),
    ("TEST-LIGHT-001", "Aputure 120d II LED Light", "Placeholder continuous LED light.", "TEST-SN-APT-001", "available", "Lighting Bay"),
    ("TEST-LIGHT-002", "Godox SL-60W LED Light", "Placeholder compact LED light.", "TEST-SN-GDX-002", "available", "Lighting Bay"),
    ("TEST-GRIP-001", "Manfrotto Video Tripod", "Placeholder fluid-head tripod.", "TEST-SN-MAN-001", "available", "Grip Room"),
    ("TEST-GRIP-002", "DJI RS 3 Gimbal", "Placeholder camera stabilizer.", "TEST-SN-DJI-002", "available", "Grip Room"),
    ("TEST-DISP-001", "Atomos Ninja V Monitor", "Placeholder on-camera monitor.", "TEST-SN-ATOM-001", "maintenance", "Service Desk"),
]


def main() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.executemany(
            """INSERT OR IGNORE INTO equipment
               (asset_code, name, description, serial_number, status, location)
               VALUES (?, ?, ?, ?, ?, ?)""",
            EQUIPMENT,
        )
        print(f"Equipment rows available: {connection.execute('SELECT COUNT(*) FROM equipment').fetchone()[0]}")


if __name__ == "__main__":
    main()
