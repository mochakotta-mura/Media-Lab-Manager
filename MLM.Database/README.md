# Media Lab Database Module

`MLM.Database.Commands.js` provides the backend’s SQLite persistence and workflow commands. It opens or creates `media-lab.sqlite` beside the module; set `MEDIA_LAB_DB` to use another path.

```js
const db = require('./MLM.Database.Commands');
```

## Public functions

### Users

- `addUser({ kreaId, name, email?, department?, role?, notificationPreferences? })`
- `updateUser(id, fields)` — supported fields: `kreaId`, `name`, `email`, `department`, `role`, `banned`, `banReason`.
- `banUser(id, reason, actorId)` / `unbanUser(id, actorId)` — update the user, record ban history, audit the action, and emit an outbox event.

### Equipment

- `addEquipment({ name, assetCode?, description?, serialNumber?, status?, location? })`
- `updateEquipment(id, fields, actorId)` — supported fields: `assetCode`, `name`, `description`, `serialNumber`, `status`, `location`.
- `find({ status?, q?, limit?, offset? })` — searches equipment by name, asset code, serial number, or description.
- `stats()` — returns equipment counts grouped by status.

### Requests and availability

- `checkAvailability(equipmentIds, startsAt, endsAt)` — returns conflicting equipment IDs.
- `createRequest({ requesterId, equipmentIds, purpose?, academicPriority?, pickupStartsAt?, pickupEndsAt?, returnStartsAt?, returnEndsAt? })` — rejects banned users and overlapping bookings; creates request items, windows, audit data, and an outbox event.
- `approveRequest(id, actorId, notes?)`
- `rejectRequest(id, actorId, reason?)`
- `cancelRequest(id, actorId)`
- `scheduleWindow({ requestId, kind?, startsAt, endsAt, status?, notes?, actorId? })`
- `requestExtension(fields)` — shorthand for `scheduleWindow` with `kind: 'extension'`.

Request status flow is generally `pending → approved → pickup_pending → picked_up → returned`; rejection and cancellation release equipment. Returned damaged equipment is marked `damaged`.

### Pickup, return, and damage

- `recordPickup({ requestId, requestItemIds?, pickedUpAt?, actorId? })`
- `markNoShow(requestId, actorId)` — marks return records as no-show and cancels the request.
- `recordReturn({ requestId, requestItemIds?, returnedAt?, condition?, damageFlag?, notes?, actorId? })`
- `recordDamage({ requestItemId, description, severity?, reportedBy? })`

When item IDs are omitted, pickup and return operations apply to every item in the request.

### Dashboard, auditing, and events

- `getDashboard()` — pending requests, all scheduled windows, and equipment.
- `getAuditHistory(entityType, entityId)`
- `getOutbox(limit?)` — unpublished integration events, capped at 1,000.
- `markEventsPublished(ids)` — marks outbox event IDs as published.

All mutating workflow operations write audit records where applicable and emit outbox events for backend notifications/integrations.

## Backend conventions

- Dates are stored as ISO-8601 strings; pass comparable ISO timestamps.
- IDs are integer database IDs, not Krea IDs or asset codes.
- The module enables SQLite foreign keys and WAL mode.
- Call `close()` during process shutdown. `db` is exported for migrations or controlled read-only queries.
- Do not commit `node_modules`, SQLite database files, or generated logs.
