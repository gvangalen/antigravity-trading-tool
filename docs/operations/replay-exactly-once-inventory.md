# Replay And Exactly-Once Inventory

Last updated: 2026-05-25

This inventory covers execution-adjacent flows where a retry, browser double-click, network replay, or worker race could otherwise create duplicate side effects.

## Hardened Flows

| Flow | Guard | Behavior On Duplicate |
| --- | --- | --- |
| Assistant pending action execute | Atomic `pending -> executing` claim in `ai_pending_actions` | Replays return stored `_execution_result` when already executed, or `409` while another request is processing. |
| Finn maintenance actions: skip/resolve/snooze/agent handoff | Deterministic action id + `ON CONFLICT (id) DO NOTHING` | Winner processes once; duplicates wait for and return the stored result or get clean `409`. |
| Manual orders | DB uniqueness on `(user_id, idempotency_key)` when key is present | Duplicate insert returns the existing manual order instead of creating another order. |
| Live manual orders | Mandatory idempotency key + risk acknowledgement + approved live preflight token | Missing/replayed unsafe context blocks before persistence. |
| Live preflight token usage | Token must be an executed `live_preflight_bot_decision` pending action, same bot, fresh timestamp, approved checks | Invalid, stale, wrong-bot, or unapproved tokens return clean `409` codes. |
| Bot decision generation | Upsert on `(user_id, bot_id, decision_date)` | Regeneration updates the same day/bot decision row instead of creating duplicate daily decisions. |
| Bot-generated execution | Atomic `planned -> executing` claim on `bot_decisions`, unique `bot_executions (user_id, bot_order_id)`, and unique execute-ledger rows per `(user_id, order_id, entry_type)` | Replays lose the claim race, duplicate execution rows collapse into the same record, and duplicate execute-ledger writes no-op before portfolio mutation. |
| Portfolio snapshots | Upsert on `(user_id, bot_id, bucket, ts)` and `(user_id, bucket, ts)` | Repeated snapshot jobs write the same time bucket. |
| Reports | Upsert on user/report natural keys | Repeated report generation updates the same report identity. |

## Still Intentional

- `ai_pending_actions.id` remains the primary idempotency key for assistant/Finn actions.
- Pending actions may enter `failed` after an execution exception; operators should request a fresh action instead of replaying a failed one.
- Live preflight tokens are reusable within their short TTL as proof of recent approved preflight. The order itself remains protected by the manual-order idempotency key.

## QA Signals

- `AiActionEngine.execute_pending_action` must claim with `UPDATE ai_pending_actions ... status = 'pending' ... RETURNING id`.
- Executed pending actions must persist `_execution_result`.
- Finn maintenance actions must continue using `_try_create_pending_action` and `_wait_for_action_result`.
- Manual orders must keep the partial unique index `ux_bot_orders_user_idempotency_key`.
- Bot execution paths must keep the `planned -> executing -> executed/failed_execution` claim boundary and the unique indexes on `bot_executions` / execute-ledger rows.
