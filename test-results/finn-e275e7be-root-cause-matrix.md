# FINN e275e7be QA repair root-cause matrix

| Priority | Visible failure | First concrete cause | Repair boundary | Safety risk | Regression proof |
| --- | --- | --- | --- | --- | --- |
| P0 | Complete setup asks again for supplied slots | Request analysis rebuilds guided state from local extraction and drops typed selector values; natural name forms are not consistently extracted. | Typed input reconciliation in operation state and request analysis. | A proposal can omit user-supplied fields or mistake model output for user input. | Complete, incomplete, ambiguous and supplied-over-derived setup cases. |
| P0 | BTC plan evaluation passes with generic content | Coverage proves evidence collection and schema fields, but does not require evidence-bound strengths, limitations and a conclusion for `evaluate_plan`. | Response planning, repair and deterministic verifier. | Generic advice could be delivered as a personal assessment. | Complete, partial, evidence-limited and generic-invalid EVALUATE drafts. |
| P1 | Evidence/reformulation/bot follow-ups do not answer | Follow-up verification reuses generic relevance checks instead of the lineage operation's safe evidence/response contract. | Lineage-aware response coverage and verifier. | Degraded context could be mistaken for a verified financial conclusion. | Verified and degraded EVALUATE to evidence/reformulation/bot chains with isolation. |
| P0 | Fresh interactive run falls back to recovery | Direct broker publish uses a hard-coded one-second deadline, giving cold synchronous Celery connection setup an unclassified timeout path. | Durable outbox direct-dispatch boundary. | Uncertain publish must not duplicate a lifecycle attempt or hide a terminal delivery failure. | Immediate publish, timeout-before-handoff, unknown acknowledgement, recovery and duplicate recovery. |

No deployment, sealed holdout, business write, or `record_accepted_release.sh` invocation is part of this repair.
