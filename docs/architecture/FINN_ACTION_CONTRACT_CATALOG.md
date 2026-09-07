# FINN V2 Action Contract Catalog

Status: canonical human-readable projection of the FINN V2 registry

Technical source of truth: `backend/domain/finn_v2_operation_registry.py`

Registry version: `2026-08-23.operation-contracts.v1`

Audit provenance: the reviewed draft is
`FINN_ACTION_CONTRACT_CATALOG_DRAFT.md` from audit commit
`638790b2f5ce8246158b75262e9ade08fea3e3aa`; its SHA-256 is
`dc7f6b31544f7b6f411372d005c0fddc59788c11006cb3d8148876308aebc64c`.

## Authority

The operation registry is the sole technical authority for a public FINN V2
operation ID, mode, input names, source scopes, policy, proposal requirement,
confirmation requirement, execution adapter, idempotency rule and
postcondition. This document is not a second schema.

The runtime contract records the selected registry contract, supplied inputs
and missing required inputs. It does not define action fields. For every run:

`missing_inputs = action_contract.required_inputs - runtime_contract.supplied_inputs`.

The selector chooses only a registered operation ID. The V2 resolver, tools,
policy, verifier, proposal service, confirmation service, execution adapter,
polling and SSE consume that resolved contract. A final operation differs from
the initial operation only through a registry-validated transition with an
explicit reason, persisted before input collection or tool planning.

## Implemented V1 Operations

| Operation | Mode and polarity | Required inputs | Evidence and result | Write boundary |
| --- | --- | --- | --- | --- |
| `create_setup` | `CREATE_PROPOSAL`, create | `setup_type`, `timeframe`, `name`, `symbol` | Active asset plus optional profile, preferences and indicators; typed setup draft | V2 proposal, confirmation, `SetupService.save_setup`, payload-hash idempotency |
| `update_setup` | `CREATE_PROPOSAL`, update | `setup_id`, `changed_fields` | Owner-scoped active setup and a typed before/after change | V2 proposal, confirmation, `SetupService.update_setup`; only its domain allowlist is accepted |
| `create_strategy` | `CREATE_PROPOSAL`, create | `setup_id`, `execution_mode`, `base_amount`; optional `name` | Owner-scoped parent setup and contextual plan evidence; typed strategy draft | V2 proposal targets the parent setup, then confirmation and `StrategyService.save_strategy`; one strategy per user/setup |
| `update_strategy` | `CREATE_PROPOSAL`, update | `strategy_id`, `changed_fields` | Owner-scoped linked strategy and typed before/after change | V2 proposal, confirmation, `StrategyService.update_strategy`; partial updates merge into the existing strategy and cannot create one |
| `watchlist_add` | `ACTION_PROPOSAL`, add | `asset` | Active asset and watchlist evidence | V2 proposal, confirmation and conflict-safe adapter; database uniqueness is `(user_id, symbol)` |
| `watchlist_remove` | `ACTION_PROPOSAL`, remove | `asset` | Active asset and watchlist evidence | V2 proposal, confirmation and owner-scoped remove adapter |
| `read_scores` | `READ`, read | Active asset from the canonical resolver when available | Existing `ScoreRepository` snapshot via `ScoreToolAdapter` as `AssetScoresData`, including source and as-of information | Read-only; no score recomputation, proposal or write |
| `explain_score` | `EVALUATE`, evaluate | Active or referenced score context | Stored score evidence with optional profile, preferences, setup, strategy and indicator context | Read-only evidence-grounded explanation; no new score, proposal or write |
| `read_portfolio` | `READ`, read | Server-issued authenticated user; optional canonical asset filter | Existing owner-scoped `BotRepository.get_portfolio_intelligence_context` through `PortfolioToolAdapter` as `PortfolioData` | Read-only; no rebalance, order or proposal |
| `evaluate_portfolio` | `EVALUATE`, evaluate | Server-issued authenticated user; optional canonical asset filter | Portfolio, profile and preferences; optional plan, market and indicator evidence | Advice-only verified or limited response; no rebalance, order, proposal or write |
| `evaluate_plan` | `EVALUATE`, evaluate | Contract-scoped plan context | Profile, preferences, asset, indicators, setup, strategy and bot evidence | Advice-only response |
| `evaluate_setup` | `EVALUATE`, evaluate | Contract-scoped setup context | Active setup, asset and optional indicator evidence | Advice-only response |
| `read_indicator_configuration` | `READ`, read | Canonical active/referenced asset | User indicator configuration | Read-only response |
| `evaluate_bot` | `EVALUATE`, evaluate | Contract-scoped bot graph | Profile, preferences, setup, strategy, bot and status evidence | Advice-only response; a bot-consequence question does not activate a bot |

`generate_strategy` is not a public FINN V2 operation. Existing legacy strategy
generation consumers remain isolated for compatibility; new FINN V2 runs use
only `create_strategy` and the V2 proposal-confirmation-execution chain.

## Runtime Attachment Audit

The following audit records the existing registry definition used by each
repaired runtime flow. It is an attachment map, not a second action schema.
The runtime must resolve exactly one listed operation contract before it
collects inputs, plans tools, proposes a change, confirms it, or executes it.

| Requested runtime flow | Canonical registry operation | Contract-derived inputs and boundary |
| --- | --- | --- |
| Create a setup | `create_setup` | Required `setup_type`, `timeframe`, `name`, `symbol`; V2 proposal, explicit confirmation and `create_setup` adapter. |
| Generate a strategy | `create_strategy` | Required `setup_id`, `execution_mode`, `base_amount`; optional `name`; V2 proposal, explicit confirmation and `create_strategy` adapter. `generate_strategy` itself is legacy-only and intentionally unavailable to new V2 runs. |
| Evaluate a plan | `evaluate_plan` | No write inputs; registry-required plan scopes and the model/verifier response contract determine the evidence-grounded read-only result. |
| Evaluate a setup | `evaluate_setup` | No write inputs; registry-required `active_asset` and `active_setup` scopes determine the evidence-grounded read-only result. |
| Read indicator configuration | `read_indicator_configuration` | No write inputs; canonical asset plus `indicator_configuration` scope determine the read-only result. |
| Evaluate a bot | `evaluate_bot` | No write inputs; registry-required bot graph scopes determine the evidence-grounded read-only result. It never implies activation. |

For every row, the runtime retains only the resolved contract identity and
typed supplied values. It derives `missing_inputs` from that contract's
`required_inputs`, stores the typed proposal/result/evidence projection, and
continues confirmation and execution only through the same contract's policy,
adapter and result path. No guided-state field list, selector validator or
conversation resolver defines a parallel action schema.

## Sources, Ownership and Freshness

Source scopes are declared in the registry and resolved by
`finn_v2_source_registry.py`. The score scope reads the existing
`daily_scores`/`ai_category_insights` source through `ScoreRepository`.

The current deployed portfolio implementation has no `PortfolioRepository` or
`portfolio_items` reader. Its canonical V1 portfolio view is the authenticated
owner-scoped query over `bot_portfolios`, `bot_configs`, `setups` and
`strategies` in `BotRepository`. The source registry records that actual reader
so later layers cannot invent a second portfolio authority. Availability,
unknown values and as-of metadata remain explicit evidence fields.

All user and entity resolution is server-side and owner-scoped. Client text
cannot provide a user ID, bypass confirmation, or replace an authenticated
target.

## Proposal and Execution Protocol

The six V1 writes use one route:

`typed draft → persisted V2 proposal → visible review → explicit confirmation → idempotent V2 execution → postcondition`.

The proposal stores user binding, target, operation, payload hash, expiry,
evidence hash and registry-derived operation semantics. The frontend uses only
the V2 `publish`, `confirm` and `execute` endpoints for a `v2_proposal`; it
does not send that proposal to the legacy assistant-action endpoint. A
server-issued confirmation token is held only during that browser request.

The originating runtime contract projects the safe proposal lifecycle
(`pending_confirmation`, `confirmed`, `blocked`, `succeeded` or `failed`) with
the immutable proposal identity and, after execution, its execution ID. It
never stores a confirmation token, action fields or a second action schema.
The same persisted terminal projection is refreshed in place so polling and
SSE expose the identical lifecycle facts.

`watchlist_add` additionally relies on the database constraint
`ux_watchlists_user_symbol`; `ON CONFLICT (user_id, symbol) DO NOTHING` makes a
replayed confirmation return the same logical result instead of inserting a
second row.

## Runtime Transition Rule

The selector intent is immutable. If contract validation must safely narrow it,
`FinnV2RuntimeContractRepository.record_final_operation` validates the change
against `FinnV2OperationRegistry.resolve_transition` and persists the final
operation, mode and reason before the contract-derived execution view is made.
Input collection then uses that final contract's required and optional inputs.
No later tool, policy, verifier or transport consumer can substitute a
different operation through a mutable `RequestPlan` field.

## Intentional V1 Gaps

The following remain unavailable and are not substituted by a generic action:

- generic setup, strategy or plan reads;
- indicator CRUD beyond existing supported contracts;
- bot CRUD, deactivation and implicit live activation;
- portfolio rebalance, manual orders and broker/exchange execution;
- review-history operations;
- a copied personal-trading database contract;
- new transport or SSE infrastructure.

Existing context-bound reads such as `read_active_setup`,
`read_linked_strategy` and `read_active_plan` remain the supported V1 read
surface.

## Verification Surface

The registry, runtime-contract, source-registry, proposal, confirmation,
execution, idempotency, lifecycle and polling/SSE test suites validate this
catalog. Provider-based development and regression checks use only the
non-sealed Build datasets. The sealed QA holdout remains QA-exclusive.
