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
- Faculty and Media Lab accounts with `@krea.edu.in` addresses.
- A four-digit PIN.

The server returns a bearer session token and also sets an HttpOnly session cookie. Sessions expire after eight hours. PIN hashes are currently held in server memory because the existing database schema does not provide a credential column; they are lost when the server restarts.

This is the current development authentication flow. Krea SSO is not implemented.

## API coverage

The server implements the operations exposed by `Media Lab Front/js/api.js`:

- Authentication: login, logout, and current-user lookup.
- Users: staff-only user creation.
- Equipment: catalog search and statistics.
- Requests: create, list, approve, reject, cancel, schedule windows, extensions, pickup, and return.
- Damage: create damage reports for request items.
- Administration: dashboard, audit history, and outbox events.

All protected API calls require the session cookie or an `Authorization: Bearer <token>` header.

## Permissions

- Students can browse equipment, create requests, view their own requests, cancel owned requests, and submit owned returns.
- Faculty and Media Lab users can review requests, approve or reject them, manage pickup and return workflows, report damage, and access administrative data.
- Requester and actor IDs supplied by the browser are ignored where the authenticated session provides the correct identity.

## Data and validation

The server delegates persistence and workflow state changes to `mlm_database_commands.Database`. These operations create the corresponding audit-log and outbox records.

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
6. Staff can record item damage.
7. History, dashboard, audit, and outbox data are loaded through the API.

Frontend-provided requester and actor IDs are not trusted; the authenticated session determines the acting user.

## Diagram coverage

The implemented server matches the core request lifecycle in the diagrams: authentication, equipment availability, request submission, approval, pickup, extensions, returns, damage, audit, and equipment-state updates.

The following diagrammed features remain outside this server:

- Krea SSO integration.
- A notification worker that consumes outbox events and sends email, SMS, or in-app notifications.
- No-show timers, overdue warning sequences, and automatic bans.
- Ban repeal workflows.
- Full lender calendar/clash visualization.

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

The server has been tested externally against a temporary SQLite database. The test client called every method exposed by `Media Lab Front/js/api.js`, including authentication, equipment, users, requests, approvals, cancellation, windows, extensions, pickup, return, damage, dashboard, audit, and outbox operations.

The workflow checks also covered booking conflicts, request ownership, staff-only authorization, logout invalidation, and protected-page redirects. These are API-level integration tests; no browser automation or formal test runner is currently included.
