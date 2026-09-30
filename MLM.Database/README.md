# Media Lab database module

This folder contains the SQLite data layer used by the backend. The Python implementation is mlm_database_commands.py and uses Python's built-in sqlite3 library.

## Initialize example data

From the repository root:

    python MLM.Database/seed_test_equipment.py

The initializer creates the schema if necessary and upserts a consistent example set without duplicating users, listings, equipment units, or example requests. It corrects seeded names, email addresses, roles, and PINs when an older local database already exists. It creates four login accounts, ten catalog listings, 24 individually tracked equipment units, and examples of a pending request, an active loan, and a damaged return.

Example PINs:

- Alex Morgan: 2468
- Priya Shah: 1357
- Maya Chen (staff): 8642
- Demo Administrator: 9999

Maya and the Demo Administrator use `@krea.edu.in`; the administrator account is `demo.admin@krea.edu.in`.

Set MEDIA_LAB_DB to initialize a different SQLite file. The initializer is for local/testing databases, not production data. Its sample images are placeholders from placehold.co and are attributed in the seed code; replace them with approved lab assets before production.

## Listings versus equipment

The listings table is the frontend catalog. One row represents a type of item and includes its quantity, category, location, description, and images. Images are stored as JSON and returned as a list of objects containing url, alt, and attribution.
Example image value:

    [{"url": "https://placehold.co/800x500/png?text=Camera", "alt": "Camera", "attribution": "Placeholder image: placehold.co"}]


The equipment table remains the authoritative inventory. Each physical unit has its own asset code, optional serial number, status, pickup history, return record, and damage reports. Equipment units link to a listing through listing_id.

For example, the catalog has one E27 LED Lightbulb listing with quantity 5, while the database has five separate E27 bulb equipment rows. If one bulb is damaged, only that unit becomes damaged and the listing reports four available units.

Database.get_listings() returns catalog rows with total_quantity, available_quantity, checked_out_quantity, lost_quantity, damaged_quantity, equipment_ids, and available_equipment_ids. Individual equipment remains available through the existing equipment methods for staff-level inventory operations.

Equipment edits use `update_equipment()`, commit to SQLite, create an audit record and outbox event, and are immediately reflected by `get_listings()`. A unit marked `lost`, `damaged`, `maintenance`, or another non-available status remains unavailable after refresh and cannot be booked.

## Python use

    from mlm_database_commands import Database

    database = Database()
    listings = database.get_listings({"status": "available"})
    database.close()

Main operations include:

- Users: add_user, update_user, ban_user, unban_user
- Listings: add_listing, get_listings
- Equipment: add_equipment, update_equipment, find, stats
- Requests: check_availability, create_request, approve_request, reject_request, cancel_request
- Lending: record_pickup, mark_no_show, record_return, record_damage
- Backend support: get_dashboard, get_audit_history, get_outbox, mark_events_published

Request data normally moves through pending, approved, pickup_pending, picked_up, and returned. Rejection or cancellation releases equipment. A damaged return marks only the affected equipment unit as damaged.

For detailed table definitions and relationships, see [schema/README.md](schema/README.md).

## Output format

The module returns Python data structures, not formatted text:

- One record: a dict with database column names.
- Collections: a list of record dictionaries.
- Request results: a request dictionary containing items and windows lists.
- get_listings: catalog dictionaries containing quantity and availability counts, unit ID lists, and an images list.
- get_dashboard: a dictionary with pendingRequests, windows, and equipment lists.
- get_outbox: event dictionaries containing event type, aggregate ID, payload, and publication timestamps.

Use json.dumps(result) when an API needs JSON output. Dates must be ISO-8601 strings, and IDs are integer database IDs.

Call close() during process shutdown. Do not commit node_modules, SQLite database files, or generated logs. The JavaScript command file is legacy; the Python module is authoritative for listings, images, authentication fields, and current database behavior.
