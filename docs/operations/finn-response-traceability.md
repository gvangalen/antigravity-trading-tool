# FINN Response Traceability

FINN attaches a privacy-safe `response_trace` to every successful normal and
streaming response. The trace explains how the answer was produced without
storing the user's prompt, response body, or raw workspace data.

## What a trace records

- selected intent, flow, route, and confidence;
- active workspace, asset, timeframe, and entity;
- data source paths, freshness status, and `as_of` timestamps;
- memory layers consulted;
- specialist contributors and final response handler;
- selected response source: database, deterministic, memory, or OpenAI;
- AI availability and the reason a model call was not used;
- fallback status and reason;
- response type and latency.

When OpenAI is disabled because no budget is available, the decision section
must report `ai_unavailable_budget`. Enabling budget is not part of this change.

## Inspecting a response

1. Copy the `trace_id` from the FINN response or server log.
2. Request `GET /api/assistant/traces/{trace_id}` while authenticated as the
   same user who produced the response.
3. Review `routing`, `context`, `data`, `memory`, `specialist`, `decision`,
   `fallback`, and `response` in order.

Trace lookup is user-scoped. A different user receives `404`, including when a
trace exists, so trace IDs cannot be used to discover another user's activity.

## Operational checks

- Search logs for `[FINN-RESPONSE-TRACE]` and the trace ID.
- Confirm the asset and timeframe match the visible workspace.
- Confirm data freshness and timestamps before investigating response wording.
- Confirm `decision.response_source` and `response.handler` match the expected
  route.
- If `fallback.used` is true, resolve its reason before changing prompts.
- Keep OpenAI disabled until call limits and controlled re-enablement have been
  tested separately.
