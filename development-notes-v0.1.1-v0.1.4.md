# Development notes — v0.1.1 to v0.1.4 (sanitized)

This public copy summarizes code changes and portable lessons. Specific devices, users, addresses, deployment events, artifact identifiers, machine paths, and operational records have been removed.

## v0.1.1

- Added a clipboard-copy fallback for plain HTTP pages outside secure browser contexts.
- Added an expand control for long text entries.
- The historical record described browser checks for both behaviors.

## v0.1.2

- Added paste handling for clipboard images. Image data starts an upload; ordinary text paste keeps the browser's normal behavior.
- The historical record described checks for image upload and text-paste behavior.

## v0.1.3

- Added a recoverable trash view with restore and permanent-delete actions.
- Added a database migration for the deletion timestamp and separate retention handling for active and deleted entries.
- Added the displayed source version and a one-time update notice.
- The historical record described API and UI checks for the trash flow.

## v0.1.4

- Added update checks for newer, version-named Windows packages and an apply flow for packaged builds.
- The apply flow verifies the copied package, replaces the running executable, restarts the application, and refreshes static assets.
- The restart path sets `PYINSTALLER_RESET_ENVIRONMENT=1` for the new packaged process.
- The historical record described API checks and packaged-flow end-to-end validation.

## Portable implementation lessons

- Clipboard APIs may be unavailable outside secure browser contexts; keep a tested fallback for local HTTP use.
- Synthetic browser events do not reproduce every trusted user gesture. Test clipboard and paste flows with a real browser interaction where those security rules matter.
- When multiple edits target one file, apply them sequentially and inspect the final file before committing.

The verification statements above summarize the original development notes. Tests were not rerun as part of sanitizing this public copy.
