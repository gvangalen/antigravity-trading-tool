# Platform Hardening Step 4 - PushService Cleanup

Last updated: 2026-05-25

Step 4 migrates PushService away from sync SQLAlchemy request/service patterns.

## What Is Complete

- `PushService` no longer imports sync `Session`.
- `PushService` no longer uses `.query()`.
- Notification lookup uses async SQLAlchemy `select`.
- Dead mobile token cleanup is async and uses `delete`.
- `notify_user_async` is the primary API for new code.
- `notify_user` remains only as a compatibility bridge for old callers.

## Compatibility Bridge

`notify_user(db, user_id, ...)` keeps the old signature but ignores the passed sync session. It opens its own async session and delegates to `notify_user_async`.

This keeps old Celery/report callers working while preventing PushService itself from carrying sync query logic.

## Follow-Up

When old callers are touched, migrate them to call:

```python
await push_service.notify_user_async(session, user_id, title, message, url)
```

or enqueue notification work into a dedicated async notification flow.
