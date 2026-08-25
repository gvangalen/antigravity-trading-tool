# FINN V2 Source-Of-Truth Ledger

Status: canonical for FINN V2 product-state reads and writes.

Operation contracts select information scopes. The code manifest at
`backend/domain/finn_v2_source_registry.py` selects the one allowed product source
for each scope. New FINN V2 runs must use both contracts; neither component may
derive a second scope, source, asset, or owner selector.

| Scope | Canonical product source | Repository | Required identity | Classification |
| --- | --- | --- | --- | --- |
| active_asset | `user_ai_preferences.selected_asset` | `AssistantContextRepository` | user | canonical product state |
| profile | `users.ai_preferences` | `TraderProfileRepository` | user | canonical product state |
| preferences | `users.ai_preferences` | `AssistantContextRepository` | user | canonical product state |
| indicator_configuration | `user_indicator_configs` | `TechnicalDataRepository` | user + symbol | canonical product state |
| active_setup | `setups` | `SetupRepository` | user + symbol | canonical product state |
| linked_strategy | `strategies` | `StrategyRepository` | user + symbol | canonical product state |
| linked_bot | `bot_configs` | `BotRepository` | user + symbol | canonical product state |
| bot_status | `bot_configs` | `BotRepository` | user + symbol | derived view |
| watchlist | `watchlists` | `WatchlistRepository` | user | canonical product state |
| portfolio | `portfolio_items` | `PortfolioRepository` | user + symbol | canonical product state |
| onboarding_status | `onboarding_steps` | `OnboardingRepository` | user | derived view |
| conversation_operation_state | `finn_v2_conversations.context_json` | `FinnV2ConversationRepository` | user + conversation | canonical product state |

## Indicator Configuration

`user_indicator_configs` is the sole product-state source for a user's enabled
technical, market, and macro indicator choices. Every runtime read and write
requires the exact canonical `user_id` and uppercase `symbol`. The table carries
the source row id, provenance, and configuration payload needed to preserve
owner-and-asset provenance into FINN V2 evidence.

The public preferences APIs, onboarding status, workspace consumers, and FINN V2
`read_indicator_configuration` all use `TechnicalDataRepository`. Asset-class and
global preference fallback are prohibited for product selection. An absent exact
symbol row is empty state, not permission to read a different asset or user.

`technical_indicator_rules`, `market_indicator_rules`, and
`macro_indicator_rules` remain system scoring definitions only. They are not
asset-scoped and cannot be migrated into user selections without independent,
verifiable user-and-symbol evidence. Historical `user_indicator_configs` rows with
`symbol IS NULL` are recorded by the migration audit and are never used by new
FINN V2 runs.

## Provenance And Cache Rules

Asset-scoped sources require `user_id + symbol`. Cache identity is at least
`user_id + symbol + operation_id + contract_version`. Tool output and evidence
preserve owner, requested symbol, resolved symbol, source record ids, source, and
run id. A mismatch is a typed fail-closed contract error; it must not be repaired
by an alternate source or a legacy fallback.

## Migration Audit

`2026_08_25_canonical_user_indicator_configs.py` normalizes unambiguous canonical
rows, adds provenance columns and canonical indexes, and records source, migrated,
ambiguous, and skipped counts in `finn_v2_data_migration_audit`. It is idempotent.
No user or asset is hardcoded, and ambiguous legacy rule rows remain audit-only.
