# Media Lab Manager Frontend

This folder contains the maintained browser frontend for the Media Lab Manager application.

## Run with the Python integration server

The frontend is served by the framework-free server in `MLM.integration/server/server.py`. Start it from the repository root:

```bash
python3 MLM.integration/server/server.py
```

Then open:

```text
http://127.0.0.1:3000/
```

Do not open the HTML files through the removed `dev-backend` server or configure a separate mock API. The frontend and API are served from the same origin.

## Frontend structure

- `index.html` — account login page.
- `pages/` — catalog, bookings, history, notifications, return, pickup-pass, and admin pages.
- `js/api.js` — shared API adapter. It defaults to `/api` and sends the HttpOnly session cookie automatically; mutating calls also send the CSRF header.
- `js/` — authentication, catalog, booking, history, return, notification, and admin behavior.
- `css/` — shared and page-specific stylesheets.
- `assets/` — frontend image assets.

## Backend integration

The frontend calls the Python server through the API methods in `js/api.js`, including:

- Authentication and session lookup.
- Equipment search and statistics.
- Booking creation and history.
- Catalog listing images are read from the database `images` JSON field and displayed on equipment cards when a valid HTTP(S) image URL is present.
- The booking cart is cleared when login changes accounts or logout succeeds; it is not shared between users.
- Approval, rejection, cancellation, pickup, return, extensions, and damage reporting.
- Dashboard, audit, and outbox data.
- The admin equipment page displays one color-coded status tag per status with its quantity. Clicking a tag edits only that group of physical units; quantity changes update existing units and preserve their serial numbers. “Remove tag” returns those units to `available`.

The server determines the authenticated requester or actor from the session; browser-supplied IDs are not authoritative.

## Authentication

- Students use `@krea.ac.in` addresses.
- Faculty and Media Lab users use `@krea.edu.in` addresses. The entire Admin Console is restricted to `demo.admin@krea.edu.in`, `bing@krea.edu.in`, and `@krea.medialab.in` accounts.
- Login requires a four-digit PIN.

For the local seed, use `maya.chen@krea.edu.in` / `8642` for staff access and `demo.admin@krea.edu.in` / `9999` for administrator access.

For API details, configuration, permissions, validation, limitations, and test coverage, see [`MLM.integration/server/README.md`](../MLM.integration/server/README.md).

## Development note

The frontend currently uses live API data for the core catalog, booking, request, return, and administration flows. Some notification, pickup-pass, settings, and lender-calendar views remain presentation/demo functionality until their corresponding backend services are implemented.
