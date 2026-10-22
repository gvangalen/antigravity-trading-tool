# FINN 2.0 agent cutover inventory

Code audit: 22 October 2026. Runtime acceptance and deployed SHA are recorded
separately in `docs/agents/FINN_RELEASE_STATUS.md`.

The old instruction to keep V1 as the primary coach is obsolete. The runtime
selector accepts only `v2_only`; `/api/assistant/chat` and its stream variant
remain compatibility URLs but deliver FINN V2. They do not run a V1 coach.

| Responsibility | Current owner in code | Remaining work |
| --- | --- | --- |
| Interactive chat and proposals | FINN V2 run, Responses tool loop and typed action contracts | Finish independent live QA for the complete multi-turn coach flow. Rename compatibility URLs only together with web and mobile clients. |
| Onboarding | Owner-scoped source refresh, Score 2.0 and report tasks | No separate onboarding AI-agent chain remains. Verify the user-facing journey independently after each release. |
| Market, macro, technical and setup match | Data/score services and `ScoreToolAdapter` for FINN reads | Keep the adapter: it reads canonical Score 2.0 data and is not an old AI agent. Verify missing, stale and complete data against Analyse, plan and Paper behavior. |
| Coach feed | Persisted events, short Luna/Responses wording and factual fallback | Feed GET and navigation do not run the model. Check deduplication and owner isolation in live QA. |
| Daily and period reports | `finn_unified_report_service` with owner-scoped facts and Luna through the Responses client | This is an asynchronous writing job, not a competing conversational coach. Check score and plan parity with FINN and Analyse. |
| Closed-trade reflection | `finn_trade_analysis_service` with owner-scoped trade evidence and a configurable Luna default through Responses | Keep for trade dossiers; test rollout, Paper and linked-exchange evidence separately. |
| Old setup agent task | `setup_task.run_setup_agent_daily` is a no-op compatibility tombstone | Remove only after queued legacy messages have drained and the worker registration/queue policy can be retired together. It cannot write a competing score. |

The old specialist, category insight, AI reflection and multi-agent master-score
services are absent from the active source tree. The old insight and reflection
tables have retirement migrations. No active Chat Completions route was found
in the listed FINN product paths; shared AI helpers use Responses.

This is a **code inventory**, not proof that every live surface is accepted.
FINN V2 still performs internal selection, relevance and verification calls;
those are part of one coach runtime and should be reduced only against measured
failure traces. The protected production QA verdict remains authoritative for
the user journey. Do not remove action confirmation, owner checks or source
identity to simplify the response path.
