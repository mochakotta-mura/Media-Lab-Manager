# Media Lab database module

This folder contains the SQLite data layer used by the backend. The Python implementation is mlm_database_commands.py and uses Python's built-in sqlite3 library.

## Basic use

    from mlm_database_commands import Database

    database = Database()
    user = database.add_user({"kreaId": "abc123", "name": "Example User"})
    equipment = database.add_equipment({"name": "Camera", "assetCode": "CAM-01"})
    database.close()

Set MEDIA_LAB_DB or pass a path to Database(path) to select another SQLite file. Foreign keys and WAL mode are enabled automatically.

## Main operations

- Users: add_user, update_user, ban_user, unban_user
- Equipment: add_equipment, update_equipment, find, stats
- Requests: check_availability, create_request, approve_request, reject_request, cancel_request
- Scheduling: schedule_window, request_extension
- Lending: record_pickup, mark_no_show, record_return, record_damage
- Backend support: get_dashboard, get_audit_history, get_outbox, mark_events_published

Request data normally moves through pending, approved, pickup_pending, picked_up, and returned. Rejection or cancellation releases the equipment. A damaged return marks the equipment as damaged.

Dates must be ISO-8601 strings. IDs are integer database IDs. Workflow changes write audit records and outbox events.

## Output format

The module returns Python data structures, not formatted text:

- One record: a dict with database column names.
- Collections: a list of record dictionaries.
- Request results: a request dictionary containing items and windows lists.
- get_dashboard: a dictionary with pendingRequests, windows, and equipment lists.
- get_outbox: event dictionaries containing event type, aggregate ID, payload, and publication timestamps.

Use json.dumps(result) when an API needs JSON output.

Call close() during process shutdown. Do not commit node_modules, SQLite database files, or generated logs.

The original JavaScript command file remains available for compatibility; new Python backend code should use the Python module and its snake_case methods.
