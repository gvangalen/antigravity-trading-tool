# Security Hardening Phase 1

Last updated: 2026-06-05

This phase closes the two critical pre-live security findings from the security review.

## Scope

### JWT and encryption secrets

- `JWT_SECRET_KEY` no longer falls back to a known default.
- Backend startup/import refuses missing, known-default, or too-short JWT secrets.
- `ENCRYPTION_KEY` raises a hard runtime error before exchange-key encryption/decryption can be used without a configured key.

### Finn action authorization

- `/api/assistant/actions/execute` no longer accepts arbitrary client-provided `{ action: ... }` payloads.
- Finn chat responses issue server-side, user-bound `action_id` tokens for executable Finn actions.
- The frontend sends only `{ action_id }` to the execute endpoint.
- Server execution loads the action payload from `ai_pending_actions` by `id + user_id`.
- Client-built agent-handoff audit payloads are no longer executable without a server-issued action id.

## Regression

```bash
pytest -q
npm run build
```

Latest local result:

- `pytest -q`: `303 passed`
- frontend build: passed

## QA Focus

1. Start backend without `JWT_SECRET_KEY`; it must fail.
2. POST a crafted payload to `/api/assistant/actions/execute`:

```json
{"action": {"type": "create_bot", "payload": {}}}
```

Expected: rejected; no side effect.

3. Generate a real Finn action through chat and execute only the returned `action_id`.
4. Confirm duplicate/replay behavior remains clean.

## Current Live Status

Live baseline on Oracle:

- commit: `4b971b2`
- `LAST_GOOD_COMMIT = 4b971b2`

What is now live-green:

- external `/api/system/health` returns `401 Missing access token`
- web login returns `auth_mode = web`, `token_transport = cookie`, and no auth tokens in the JSON body
- mobile login returns `auth_mode = mobile`, `token_transport = body+cookie`, and includes rotated access/refresh tokens in the JSON body
- refresh rotation works for both web and mobile
- logout invalidates refresh tokens
- Mission Control nested Finn actions expose real `action_id`
- second Finn execute returns explicit `replayed = true`
- rate limits are live on:
  - `/api/assistant/actions/execute`
  - `/api/orders/manual`
  - `/api/orders/manual/preflight`

What is now also regression-backed:

1. authenticated frontend flows clear local user/token state on logout and failed refresh
2. login overwrites the local user snapshot instead of preserving stale user identity
3. market-data GET routes no longer trigger forward-return sync writes on data misses
