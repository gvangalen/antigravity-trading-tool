# Security Hardening Phase 1

Last updated: 2026-05-25

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
