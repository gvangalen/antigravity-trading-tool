# FINN 2.0 release and rollback pointer

The former Block 8 V1-to-V2 cutover procedure is retired. Current code accepts
only `FINN_V2_RUNTIME_MODE=v2_only`; setting `v1_primary` cannot restore a V1
coach. The old rollback instruction in this file was therefore unsafe.

For every FINN release, follow the canonical
[`FINN_RELEASE_PROCESS.md`](../agents/FINN_RELEASE_PROCESS.md) and the active
candidate in [`FINN_RELEASE_STATUS.md`](../agents/FINN_RELEASE_STATUS.md).
Build completes the local action, provider and product gates; CI and Auto
Deploy publish the exact candidate; independent QA owns authenticated runtime
acceptance. The current code inventory is in
[`finn-core-v2-legacy-retirement-matrix.md`](../architecture/finn-core-v2-legacy-retirement-matrix.md).

If a release must be rolled back, redeploy the last known good **V2** commit
through the deployment workflow and verify backend health, frontend build info
and matching SHA. Stop action execution with the current action flags if the
incident concerns writes or trading. Do not use V1 runtime flags or an old
agent path as a rollback mechanism.
