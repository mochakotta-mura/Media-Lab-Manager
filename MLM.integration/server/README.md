# Media Lab Manager Python Server

`server.py` is the framework-free Python HTTP server for the Media Lab Manager application. It serves the maintained frontend in `Media Lab Front` and exposes the JSON API expected by `Media Lab Front/js/api.js`.

The integration is contained in `MLM.integration`; existing frontend and database files are used without modification. The former `Media Lab Front/dev-backend` Node development server has been removed.

## Requirements

- Python 3.10 or newer
- The repository database module at `MLM.Database/mlm_database_commands.py`
- No third-party Python packages

## Start the server

From the repository root:

```bash
python3 MLM.integration/server/server.py
```

The default address is:

```text
http://127.0.0.1:3000
```

Open the root URL in a browser. The server serves `Media Lab Front/index.html` and its protected application pages.

The frontend and API use the same origin, so no `mlmApiBase` local-storage setting or separate development backend is needed. The frontend API adapter uses `/api` automatically.

For a local demo database, seed the repository database before starting the server:

```bash
python3 MLM.Database/seed_test_equipment.py
python3 MLM.integration/server/server.py
```

The seed script provides demo students, staff, an administrator, equipment, and example requests. Demo PINs are printed by the script.

## Configuration

Use environment variables to change the server settings:

```bash
HOST=127.0.0.1 PORT=3000 MEDIA_LAB_DB=/path/to/media-lab.sqlite \
  python3 MLM.integration/server/server.py
```

- `HOST` controls the listening address.
- `PORT` controls the HTTP port.
- `MEDIA_LAB_DB` selects the SQLite database used by `mlm_database_commands.py`.

## Authentication

The login endpoint accepts:

- Students with `@krea.ac.in` addresses.
- Faculty with `@krea.edu.in` addresses.
- Presentation administrators with `@krea.medialab.in` addresses.
- A four-digit PIN.

The server sets an HttpOnly, SameSite=Strict session cookie. In production the cookie is also Secure; local HTTP development can explicitly set `COOKIE_SECURE=false`. Session records and scrypt PIN hashes are persisted in SQLite, and sessions expire after eight hours.

This is the current development authentication flow. Roles are assigned from the email domain for the presentation: `@krea.ac.in` becomes `student`, `@krea.edu.in` becomes `faculty`, and `@krea.medialab.in` becomes `admin`. Krea SSO is not implemented.

## API coverage

The server implements the operations exposed by `Media Lab Front/js/api.js`:

- Authentication: login, logout, and current-user lookup.
- Users: staff user listing and administrator-only user creation (new users default to student).
- Equipment: catalog search, statistics, creation, and updates.
- Settings: administrator-only settings read and update.
- Requests: create, list, approve, reject, cancel, schedule windows, extensions, pickup, return submission, return verification, and legacy staff return processing.
- Damage: create damage reports for request items.
- Administration: dashboard, audit history, and outbox events.

All protected API calls require the session cookie. Mutating requests also require the `X-MLM-CSRF: 1` custom header; this is a defense-in-depth CSRF check alongside SameSite=Strict cookies.

## Permissions

- Students can browse equipment, create requests, view their own requests, cancel owned requests, and submit owned returns.
- Faculty and Media Lab users can review requests, approve or reject them, manage pickup and return workflows, report damage, and access administrative data.
- Requester and actor IDs supplied by the browser are ignored; the authenticated session determines the acting user.

## Data and validation

The server delegates persistence and workflow state changes to `mlm_database_commands.Database`. These operations create the corresponding audit-log and outbox records.

At startup, the server also creates the `return_submissions` table used for student return submissions and staff verification when it is missing.

The HTTP layer validates:

- JSON request bodies.
- ISO-8601 date values and date ordering.
- Equipment reservation overlap.
- Request ownership.
- Staff-only operations.
- Protected frontend page access.

Reservation checks reject equipment that is not available and detect both complete and partial time-window overlaps.

## Frontend workflow

The server supports the live-data paths used by the maintained frontend:

1. A user signs in through `index.html`.
2. The catalog loads equipment from `/api/equipment`.
3. The booking page submits equipment and ISO-8601 time windows.
4. Staff review pending requests and approve or reject them.
5. Staff confirm pickup; the requester or staff records the return.
6. Student return submissions remain pending until staff verification.
7. Staff verify returns as `verified_returned`, `verified_damaged`, `missing_items`, or `disputed_return`.
8. History, dashboard, audit, and outbox data are loaded through the API.

Frontend-provided requester and actor IDs are not trusted; the authenticated session determines the acting user.

## Server function blocks

The documented function groups in `server.py` are:

- Security helpers: PIN hashing, token hashing, cookies, login lockouts, and role checks.
- Data helpers: date parsing, request lookup/listing, and equipment availability validation.
- HTTP helpers: JSON responses, cookies, sessions, request bodies, and error handling.
- HTTP methods: CORS preflight and GET, POST, PATCH, and PUT dispatch.
- API routing: authentication, equipment, settings, users, requests, returns, damage, audit, dashboard, and outbox operations.
- Lifecycle functions: protected static-file serving and server startup/shutdown cleanup.

## Diagram coverage

The implemented server matches the core request lifecycle in the diagrams: authentication, equipment availability, request submission, approval, pickup, extensions, returns, damage, audit, and equipment-state updates.

The following diagrammed features remain outside this server:

- Krea SSO integration.
- A notification worker that consumes outbox events and sends email, SMS, or in-app notifications.
- No-show timers, overdue warning sequences, and automatic bans.
- Ban repeal workflows.
- Full lender calendar/clash visualization.

## Return confirmation workflow

The server supports two-party return confirmation through:

```text
POST /api/requests/{id}/return-submission
GET  /api/requests/{id}/return-submission
POST /api/requests/{id}/return-verification
```

Student submissions include the claimed return time, condition, damage description, missing-item information, and photo references. Staff verification records the actual return time, staff condition, notes, verification status, and verification photo references.

For compatibility with the current frontend, a student `POST /api/requests/{id}/return` is treated as a return submission. Staff can still use that route for legacy direct processing. Actual photo upload and file storage are not implemented; the API stores references only.

Errors are returned as JSON:

```json
{"error":"Human-readable error message"}
```

## Development check

Compile-check the server without starting it:

```bash
python3 -m py_compile MLM.integration/server/server.py
```

## Integration test coverage

The server has been tested externally against a temporary SQLite database and the seeded local database. The test client called every method exposed by `Media Lab Front/js/api.js`, including authentication, equipment, users, requests, approvals, cancellation, windows, extensions, pickup, return submission, return verification, damage, dashboard, audit, and outbox operations.

The workflow checks also covered booking conflicts, request ownership, staff-only authorization, logout invalidation, and protected-page redirects. These are API-level integration tests; no browser automation or formal test runner is currently included.
