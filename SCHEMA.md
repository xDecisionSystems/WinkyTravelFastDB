# SCHEMA.md

Canonical database schema reference for Winky Travel FastDB.

## Maintenance Rule

If any table/column/index/constraint/relationship changes in code, update this file in the same change.

Source of truth in code:

- `services/postgres.py` (`_create_schema`)

## Database

- Engine: PostgreSQL
- Connection: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` (legacy `DATABASE_URL` also supported)

## Tables

### `users`

- `user_id` `TEXT` primary key
- `email` `TEXT` nullable
- `name` `TEXT` nullable
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `usage_logs`

- `id` `BIGSERIAL` primary key
- `user_id` `TEXT` not null
- `endpoint` `TEXT` not null
- `provider` `TEXT` not null
- `status_code` `INTEGER` not null
- `request_summary` `JSONB` not null
- `created_at` `TIMESTAMPTZ` not null

### `trips`

- `id` `TEXT` primary key
- `owner_user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `trip_name` `TEXT` not null
- `location` `TEXT` not null
- `start_date` `DATE` not null
- `end_date` `DATE` not null
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `trip_shares`

- `id` `BIGSERIAL` primary key
- `trip_id` `TEXT` not null references `trips(id)` on delete cascade
- `shared_with_user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `shared_by_user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `can_view` `BOOLEAN` not null default `TRUE`
- `can_add` `BOOLEAN` not null default `FALSE`
- `can_delete` `BOOLEAN` not null default `FALSE`
- `can_edit` `BOOLEAN` not null default `FALSE`
- `can_owner` `BOOLEAN` not null default `FALSE`
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null
- unique `(trip_id, shared_with_user_id)`
- check `(can_view = TRUE)`
- check `(can_owner = FALSE OR (can_view = TRUE AND can_add = TRUE AND can_delete = TRUE AND can_edit = TRUE))`

### `activities`

- `id` `TEXT` primary key
- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `trip_id` `TEXT` nullable references `trips(id)` on delete cascade
- `name` `TEXT` not null
- `type` `TEXT` not null
- `notes` `TEXT` not null default `''`
- `scheduled_day` `DATE` nullable
- `scheduled_time` `TIME` nullable
- `time_of_day` `TEXT` nullable check in `('morning', 'afternoon', 'evening')`
- `attachments` `JSONB` not null default `'[]'::jsonb`
- `custom_type_name` `TEXT` nullable
- `custom_icon` `TEXT` nullable
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `travels`

- `id` `TEXT` primary key
- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `trip_id` `TEXT` nullable references `trips(id)` on delete cascade
- `type` `TEXT` not null
- `departure` `TEXT` not null
- `arrival` `TEXT` not null
- `date` `DATE` not null
- `time` `TIME` not null
- `confirmation_number` `TEXT` not null default `''`
- `notes` `TEXT` not null default `''`
- `attachments` `JSONB` not null default `'[]'::jsonb`
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `hotels`

- `id` `TEXT` primary key
- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `trip_id` `TEXT` nullable references `trips(id)` on delete cascade
- `name` `TEXT` not null
- `address` `TEXT` not null
- `check_in` `DATE` not null
- `check_out` `DATE` not null
- `confirmation_number` `TEXT` not null default `''`
- `notes` `TEXT` not null default `''`
- `attachments` `JSONB` not null default `'[]'::jsonb`
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `transits`

- `id` `TEXT` primary key
- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `trip_id` `TEXT` nullable references `trips(id)` on delete cascade
- `type` `TEXT` not null
- `from_location` `TEXT` not null default `''`
- `to_location` `TEXT` not null default `''`
- `notes` `TEXT` not null default `''`
- `attachments` `JSONB` not null default `'[]'::jsonb`
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `schedule_items`

- `id` `TEXT` primary key
- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `trip_id` `TEXT` not null references `trips(id)` on delete cascade
- `day_date` `DATE` not null
- `display_order` `INTEGER` not null default `0`
- `item_type` `TEXT` not null check in `('activity', 'travel', 'hotel', 'transit')`
- `item_id` `TEXT` not null
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null
- unique `(trip_id, day_date, display_order)`

### `custom_activity_types`

- `id` `TEXT` primary key
- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `name` `TEXT` not null
- `icon` `TEXT` not null
- `is_default` `BOOLEAN` not null default `FALSE`
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null

### `activity_icon_overrides`

- `user_id` `TEXT` not null references `users(user_id)` on delete cascade
- `activity_type_id` `TEXT` not null
- `icon` `TEXT` not null
- `created_at` `TIMESTAMPTZ` not null
- `updated_at` `TIMESTAMPTZ` not null
- primary key `(user_id, activity_type_id)`

### `rate_limit_events`

- `id` `BIGSERIAL` primary key
- `subject_type` `TEXT` not null
- `subject_key` `TEXT` not null
- `endpoint` `TEXT` not null
- `client_ip` `TEXT` not null
- `user_id` `TEXT` nullable
- `allowed` `BOOLEAN` not null
- `reason` `TEXT` nullable
- `created_at` `TIMESTAMPTZ` not null

## Indexes

- `idx_usage_logs_user_created_at` on `usage_logs (user_id, created_at DESC)`
- `idx_usage_logs_endpoint_created_at` on `usage_logs (endpoint, created_at DESC)`
- `idx_trips_owner_start_date` on `trips (owner_user_id, start_date)`
- `idx_trip_shares_shared_with_user` on `trip_shares (shared_with_user_id, trip_id)`
- `idx_trip_shares_trip_id` on `trip_shares (trip_id)`
- `idx_activities_user_trip` on `activities (user_id, trip_id)`
- `idx_activities_trip_scheduled_day` on `activities (trip_id, scheduled_day)`
- `idx_activities_type` on `activities (type)`
- `idx_travels_trip_datetime` on `travels (trip_id, date, time)`
- `idx_hotels_trip_checkin` on `hotels (trip_id, check_in)`
- `idx_transits_trip` on `transits (trip_id)`
- `idx_schedule_items_trip_day_order` on `schedule_items (trip_id, day_date, display_order)`
- `idx_schedule_items_lookup` on `schedule_items (item_type, item_id)`
- `idx_custom_activity_types_user` on `custom_activity_types (user_id)`
- `idx_rate_limit_events_subject_allowed_created_at` on `rate_limit_events (subject_type, subject_key, allowed, created_at DESC)`
- `idx_rate_limit_events_created_at` on `rate_limit_events (created_at DESC)`
