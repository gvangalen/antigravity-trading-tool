# FINN Strategy Domain Contract

Status: canonical implementation note for the existing `create_strategy`,
`update_strategy`, and `delete_strategy` action contracts.

`finn_v2_operation_registry.py` remains the authority for operation identity,
required inputs, confirmation, execution, and idempotency. This document
records how its strategy fields map to the persisted child domain; it does not
introduce a parallel action contract.

## Relationship

Each strategy has exactly one owner-scoped `setup_id`. A setup can have zero or
more strategies. Names are unique per `(user_id, setup_id, canonical_name)`.
The database migration `2026_09_14_strategy_domain_multiple_strategies.py`
preserves existing rows and gives legacy rows a canonical name and their
historical setup asset/timeframe.

## Fields

| Field | Type | Input rule | Storage and public response |
| --- | --- | --- | --- |
| `strategy_id` | integer | Generated; immutable | `strategies.id`, returned as `id` and `strategy_id` |
| `setup_id` | integer | Required for create; immutable for update | `strategies.setup_id`; owner-scoped parent validation |
| `name` | string | Optional on create, mutable on update | `strategies.name`; canonical comparison in `canonical_name` |
| `symbol` | canonical ticker | Optional; explicit input wins | `strategies.symbol`; falls back to setup symbol with `asset_source=setup_default` |
| `timeframe` | string | Optional; explicit input wins | `strategies.timeframe`; falls back to setup timeframe with `timeframe_source=setup_default` |
| `execution_mode` | `fixed` or `custom` | Required for create; mutable | `strategies.execution_mode`; custom requires a decision curve |
| `base_amount` | positive number | Required for create; mutable | `strategies.base_amount` |
| `entry`, `stop_loss`, `targets` | numeric / array | Required for executable trade or position strategies | dedicated strategy columns and `data`; FINN drafts may be non-executable until supplied |
| `risk_profile`, `entry_type`, `automation`, `decision_curve` | typed JSON-compatible values | Optional and mutable when accepted by the existing service allowlist | `strategies.data` plus relevant existing columns |

## Defaults and Safety

Only `symbol` and `timeframe` may be derived from the confirmed parent setup.
Their sources are retained in persisted strategy data. Strategy creation always
uses the existing proposal, confirmation, execution, and idempotency contract.
No strategy write is allowed before confirmation; no strategy action enables a
broker order, live trading, or a live bot.
