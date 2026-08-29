# FINN 7bdeef0e QA repair root-cause matrix

Evidence source: independent QA report and raw production results captured for
`7bdeef0e19f039f4943bf1f9204e5b0f6f74cc82`.

| Priority | Failure | First concrete cause | Canonical boundary | Proof |
| --- | --- | --- | --- | --- |
| P1 | `watchlist_add` and `activate_bot` have inconsistent polarity expectations | The registry declares only lexical selector eligibility while classification projects a different hard-coded lifecycle action; eval cases can declare either vocabulary independently. | OperationContract polarity specification, eval validator, classification projection and policy/proposal consumers. | Registry-driven eval expectations reject aliases and runtime action projection is contract-derived. |
| P1 | Capability and live automation paraphrases misclassify | Preprocessor semantic facts do not recognize the general capability noun phrase or automation-live act, leaving the model an unhelpful fact/manifest context. | Fact normalization and structured selector manifest, never a local operation router. | Semantically distinct capability and automation regression cases. |
| P1 | Cosmos is not canonical ATOM | The central default asset catalog does not contain the Cosmos canonical symbol/display mapping, so selector projection preserves provider prose. | Shared asset catalog resolver before target/proposal/tool projection. | Catalog and structured-selection ATOM tests. |
| P1 | SSL, bad descriptor and closed-loop errors in FINN worker | A prefork child repeatedly combines task-local `asyncio.run()` loops with process-global async SQLAlchemy pools. Disposing only the sync facade leaves loop-bound async connections alive. | FINN worker task loop wrapper and async engine lifecycle. | Sequential task-loop disposal, retry/recovery and restart regressions. |
| P2 | Multiple LAST_GOOD files act as truth | Deploy and rollback retain repo and web-root mirrors in addition to an unversioned host marker. | One canonical marker plus explicit accepted-release command that updates mirrors atomically. | Acceptance command and marker-policy tests; candidate deploy path leaves marker unchanged. |

No holdout dataset is changed or executed by this repair. Policy semantics remain
unchanged: live activation and autonomous fund movement are classified as
execute intent but remain blocked when high-risk policy controls deny them.
