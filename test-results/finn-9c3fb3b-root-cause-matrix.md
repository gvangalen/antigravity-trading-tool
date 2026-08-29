# FINN 9c3fb3b QA repair root-cause matrix

Evidence source: independent QA report, raw selector results, lifecycle trace,
runtime trace, and sealed manifest hashes captured for production release
`9c3fb3b005674ff6b9a9cbf5467198ca1b0bc738`.

| Priority | Visible failure | First concrete cause | Repair boundary | Safety risk | Regression proof |
| --- | --- | --- | --- | --- | --- |
| P1 | Natural plan evaluation becomes clarification | The selector receives insufficiently generalized evaluation facts and the post-selection validator rejects a valid canonical result using a raw request verb. | Request fact normalization and registry-backed validation. | A valid read-only evaluation is unavailable; no write may be inferred. | Natural plan-evaluation variants retain `evaluate_plan`; genuinely unspecified change requests clarify. |
| P1 | Live automation becomes a bot read | Activation language is not consistently normalized as an operation request before the model sees the immutable manifest. | Request fact normalization and structured selector projection. | Live activation must remain confirmation- and policy-gated. | Activation, status-read and linked-bot read variants stay disjoint. |
| P1 | NEAR target is null despite canonical entity | A canonical entity target can be replaced by a nullable structured `target_asset` field after asset resolution. | Typed selector target projection and shared target resolver. | A write proposal could lose its explicit user target. | NEAR, ATOM, POL, UNI and ticker/display-name add/remove cases. |
| P1 | `operation_action_mismatch` after correct projection | The validator re-applies lexical `allowed_action_polarities` to raw preprocessor facts after the selected contract already projected the canonical enum. | OperationContract registry validator. | A valid safe contract can be rejected; invalid projected polarity still must fail closed. | All canonical polarity families plus deliberate mismatch cases. |
| P1 | EVALUATE repair downgrades a grounded answer | Repair/verifier coverage does not preserve grounded answer sections or require a concrete next step in the final repaired response. | Response repair and verifier coverage contract. | Weakening evidence/safety checks would expose unsupported claims. | Full, partial, noncritical-claim and still-invalid repair cases. |
| P2 | Safe downgrade breaks immediate follow-ups | Only verified conclusions enter lineage; no typed degraded context carries safe metadata/evidence availability. | Typed conversation lineage state. | An unverified conclusion must never become a fact. | Evidence, reformulation and bot follow-up use limited degraded context without cross-user/asset leakage. |
| P2 | Rollback markers disagree | Historic repository marker is a stale mirror while host marker is canonical but historical acceptance provenance is not proven in code. | Operations marker policy and documentation, not candidate deployment. | Incorrect rollback target if a stale mirror is trusted. | One writer and read-only canonical marker tests; no marker mutation in this repair. |

No deployment, sealed-holdout execution, business write, or
`record_accepted_release.sh` invocation is part of this repair.
