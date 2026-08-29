# FINN 5b041e1c QA repair root-cause matrix

Source evidence: independent QA report and `runtime-blocker.json` captured on
2026-08-29 for production candidate `5b041e1c7199458dbb577affc9462d9f1ab7ff07`.

| Priority | Observed failure | First concrete cause | Canonical repair boundary | Regression proof |
| --- | --- | --- | --- | --- |
| P0 | Fresh run remained `created` for more than ten minutes | A successful broker publish called `mark_dispatched`; `dispatched` did not mean a worker had claimed the row. | FINN durable dispatch repository and worker handover. Only `claim()` may create a claimed/running state. | Publish timeout, publish-without-claim, worker crash, and bounded terminal failure tests. |
| P0 | Recovery replayed stale rows ahead of fresh interactive work | Recovery selected old `dispatched` rows in FIFO order and republished them every minute without an ownership transition or stale terminalization. | Outbox recovery policy. Fresh pending work is preferred; stale unclaimed records are terminalized through one idempotent procedure. | Stale backlog and fresh-interactive-priority tests. |
| P0 | SSL transport/event-loop failures accumulated in the sole AI worker | Recovery and interactive FINN work shared the throttled `ai_generation` queue; worker process loop resources were reused across repeated async task execution. | FINN queue policy and task loop lifecycle. | Queue isolation and worker restart/recovery tests. |
| P0 | Rollback provenance differs between production locations | Two `LAST_GOOD_COMMIT` files are maintained independently. | Deployment marker helper and explicit acceptance update procedure. | Marker consistency test; marker update remains gated on independent QA acceptance. |
| P1 | Polygon and Uniswap were not canonical targets | The default asset catalog lacks `POL` and `UNI`, so model strings bypass canonical target projection. | Shared asset catalog resolver. | Canonical asset resolver and selector-projection tests. |
| P1 | Write polarity varied as `add`/`activate`/`read` | Runtime projection used product verbs rather than one contract-derived action polarity enum. | Operation contract and classification projection. | Watchlist, live-bot, and unsupported execute-intent tests. |
| P1 | Complete setup lost `setup_type`, `timeframe`, and `name` | Strict selector entity schema did not expose those contract-required typed fields. | Structured selector schema and contract-bound missing-input reconciliation. | Complete setup extraction test. |
| P1 | General capability wording selected off-topic | Capability relies on too narrow preprocessed discourse facts. | Preprocessor semantic fact extraction, not operation routing. | Generic capability phrasing test. |

Non-causes: provider availability, strict schema transport, parse, and
validation all passed in the independent direct-selector canary. No product
tools, proposals, writes, or executions were reached during the blocked run.
