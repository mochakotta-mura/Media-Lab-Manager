# Database schema reference

The schema is created by `mlm_database_commands.py` and stored in SQLite. The main database README covers setup and API usage; this file explains what each table represents and how the tables connect.

The rendered diagram is [database_schema.svg](database_schema.svg), and its editable Mermaid source is [database_schema.mmd](database_schema.mmd).

## Tables

### users

Stores people who can use or administer the system.

- `id` is the database identifier.
- `krea_id` and `email` identify the person; both are unique.
- `role` controls broad permissions such as student, staff, or admin.
- `pin_hash`, `failed_pin_attempts`, and `locked_until` support PIN login protection.
- `banned` and `ban_reason` store the current ban state.
- `notification_preferences` is JSON stored as text.

Users are referenced by sessions, requests, ban history, damage reports, and audit records.

### sessions

Stores active authenticated sessions. `token_hash` is unique, and `user_id` points to the session owner. Expired sessions can be removed without changing the user account.

### auth_attempts

Tracks failed login attempts by IP address and email. The combined `ip_address` plus `email` value is unique, allowing the server to apply temporary lockouts.

### lab_settings

Stores system-wide configuration as key-value pairs rather than hardcoded settings.

- `setting_key` is the unique setting name, such as `standard_loan_hours`.
- `setting_value` stores the value as text, such as `72` or `true`.
- `updated_at` records when the setting was last changed.

The Python API exposes these values through `get_settings()` and `update_settings()`.

### listings

Represents the catalog-level description of an item type. A listing is what a frontend displays as one catalog card.

- `listing_code` is the stable catalog code.
- `name`, `description`, `category`, and `location` describe the catalog item.
- `quantity` is the intended catalog quantity.
- `images` is JSON text containing a list of objects with `url`, `alt`, and `attribution`.

Listings do not represent individual loans or damage states. Those are stored in `equipment`.

### equipment

Represents one physical, separately trackable unit. This table is authoritative for reservations, pickup, returns, and damage.

- `listing_id` links the unit to its catalog listing.
- `asset_code` is the unique inventory code.
- `serial_number` is an optional unique manufacturer serial number.
- `status` records availability, pickup, overdue, damage, maintenance, retirement, or loss.
- `location` records where the unit is stored.

For example, one listing can describe five identical lightbulbs while five equipment rows preserve separate damage histories.

### tags and equipment_tags

`tags` stores reusable labels. `equipment_tags` is the join table connecting equipment to tags. Its pair of foreign keys is also its composite primary key, so the same tag cannot be attached to the same unit twice.

### requests

Represents a borrower’s overall booking request.

- `requester_id` points to the user who submitted it.
- `purpose` and `academic_priority` support review and prioritization.
- `status` tracks the request lifecycle: pending, approved, rejected, cancelled, pickup_pending, picked_up, returned, overdue, or completed.
- `rejection_reason` and `approval_notes` preserve staff decisions.

One request can contain multiple request items and time windows.

### request_items

Connects a request to one individual equipment unit. `request_id` plus `equipment_id` is unique, preventing the same unit from appearing twice in one request. Item-level status allows each unit to be tracked separately.

### time_windows

Stores requested or approved pickup, return, and extension periods for a request. `starts_at` and `ends_at` are ISO-8601 text timestamps and are checked for overlapping bookings.

### returns

Stores pickup and return details for one request item. `request_item_id` is unique, so each item has at most one return record. It includes condition, damage, no-show, and overdue-warning information.

### damage_reports

Stores detailed damage reports against request items. `reported_by` optionally identifies the user or staff member who filed the report. A report does not replace the equipment status; the database also marks the affected physical unit as damaged.

### ban_history

Stores every ban or unban action. `user_id` identifies the affected user, while `actor_id` identifies who performed the action.

### audit_log

Stores a general history of important actions. `actor_id` identifies the user who acted. `entity_type` and `entity_id` identify the affected object, such as a request or equipment unit. Because the entity can be different types, SQLite does not enforce a foreign key for `entity_id`.

### outbox_events

Stores events for notifications and integrations. `event_type`, `aggregate_type`, and `aggregate_id` identify the event; `payload` contains JSON text. An event is unpublished while `published_at` is null and is marked after successful delivery.

## Common relationships

- One user has many sessions and requests.
- One listing has many individual equipment units.
- One request has many request items and time windows.
- One request item refers to one equipment unit and can have one return record.
- One request item can have multiple damage reports.
- Equipment and tags have a many-to-many relationship through `equipment_tags`.
