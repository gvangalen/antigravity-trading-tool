# FINN 991dc03f QA Repair Root-Cause Matrix

| QA symptom | First concrete cause | Central repair | Regression evidence |
| --- | --- | --- | --- |
| `position` / `dagbasis` setup asked for slots that were present | V2 slot extraction only accepted coded timeframes and collapsed natural setup types to `trade`; classification passed a case-folded string and lost the display name | `FinnV2SetupInputCatalog` normalizes only typed values. The preprocessor retains original text for display slots, while comparison normalization remains separate. Execution services accept the canonical `position` type. | `test_setup_catalog_canonicalizes_natural_slots_without_losing_user_display_name`, multilingual catalog cases |
| BTC plan evaluation reported `missing_required_scope_refs: preferences` despite a completed artifact | Prompt references were projected by tool names while validation used persisted scope semantics, leaving two non-identical evidence contracts | `canonical_evidence_scope` is now shared by context construction and validation; aliases normalize before the tool-bound canonical scope is compared. | `test_integrated_plan_recognizes_preferences_alias_as_the_canonical_scope` plus existing scope coverage and ingestion tests |
| Generic bot-plan text became reusable verified context | A passed verifier status and any refs were treated as sufficient lineage promotion | Verifier records explicit `lineage_eligible` provenance only after full evidence and response coverage. Canonical conversations require that proof before promotion. | `test_canonical_context_does_not_promote_generic_bot_text_without_lineage_proof` |

No deployment, sealed holdout execution, business write, or `LAST_GOOD_COMMIT` update is part of this repair branch.
