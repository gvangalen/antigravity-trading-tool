# FINN 7bdeef0e QA repair root-cause matrix

Evidence source: independent QA report and raw production results captured for
`7bdeef0e19f039f4943bf1f9204e5b0f6f74cc82`.

| Priority | Failure | First concrete cause | Canonical boundary | Proof |
| --- | --- | --- | --- | --- |
| P1 | `watchlist_add` and `activate_bot` have inconsistent polarity expectations | The registry declares only lexical selector eligibility while classification projects a different hard-coded lifecycle action; eval cases can declare either vocabulary independently. | OperationContract polarity specification, eval validator, classification projection and policy/proposal consumers. | Registry-driven eval expectations reject aliases and runtime action projection is contract-derived. |
| P1 | Capability and live automation paraphrases misclassify | Preprocessor semantic facts do not recognize the general capability noun phrase or automation-live act, leaving the model an unhelpful fact/manifest context. | Fact normalization and structured selector manifest, never a local operation router. | Semantically distinct capability and automation regression cases. |
| P1 | Cosmos is not canonical ATOM | The central default asset catalog does not contain the Cosmos canonical symbol/display mapping, so selector projection preserves provider prose. | Shared asset catalog resolver before target/proposal/tool projection. | Catalog and structured-selection ATOM tests. |
| P1 | SSL, bad descriptor and closed-loop errors in FINN worker | A prefork child repeatedly combines task-local `asyncio.run()` loops with process-global async SQLAlchemy pools. Disposing only the sync facade leaves loop-bound async connections alive. | FINN worker task loop wrapper and async engine lifecycle. | Sequential task-loop disposal, retry/recovery and restart regressions. |
| P2 | Multiple LAST_GOOD files act as truth | Deploy and rollback retain repo and web-root mirrors in addition to an unversioned host marker. | One canonical host marker plus an explicit accepted-release command with an atomic replacement. | Acceptance command and marker-policy tests; candidate deploy path leaves marker unchanged. |

## Candidate provider evidence

The direct selector sample ran in a detached temporary server checkout at
`933ec6ed8bb25134510a313819fc7832a6f036d8`; no PM2 process, deployment,
conversation, tool, proposal, or write path was used. Three development and
three regression cases all returned HTTP `200` / `completed`, a response ID,
and passed structured parse and contract validation. The raw per-call trace is
stored beside this matrix in `finn-7bdeef0e-direct-selector-sample.json`.

No holdout formulation was added, changed, or executed by this repair; its
existing expected polarity labels were migrated to the canonical enum so the
registry can reject alternate internal vocabulary before execution. Policy semantics remain
unchanged: live activation remains an `activate` intent and autonomous fund
movement an `execute` intent; both remain blocked when high-risk policy
controls deny them.
