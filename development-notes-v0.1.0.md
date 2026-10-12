# Development notes — v0.1.0 (sanitized)

This public copy keeps portable implementation notes. Device names, user identities, network addresses, deployment records, and machine-specific operations have been removed.

## Initial implementation

- A FastAPI service with SQLite storage and a static JavaScript interface.
- Text entries, multi-file uploads, image previews, item listing, downloads, and deletion.
- Optional password access using PBKDF2-HMAC-SHA256 and signed session cookies.
- Configurable listening port, local instance address display, and per-instance data storage.
- A packaged Windows build and optional current-user startup helpers.

The initial version used a seven-day retention period. Later versions changed the default and added a configurable retention setting; see the current user documentation for present behavior.

## Historical verification note

The original development record described local API checks for health, text and file transfer, deletion, and password access, plus a packaged-app smoke check. Those checks are historical notes and were not rerun while preparing this public copy.
