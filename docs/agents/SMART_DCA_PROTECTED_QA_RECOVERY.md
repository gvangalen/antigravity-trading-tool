# Smart DCA protected QA recovery

Status: operational procedure for the `smart_dca_journey` profile

The protected journey creates one permanently inactive child under the
owner-bound QA fixture. It confirms configuration only. A failed cleanup
deactivates the child bot where the exact marker and namespace can be
verified, then retains the child for investigation. A retained child must
never be used for another functional journey.

If `fixture_state=quarantined` or `quarantine_unverified`:

1. Stop functional runs for this profile. Record the workflow run ID, attempt,
   public release SHA and sanitized artifact hash. Keep the namespace within
   the protected QA process; do not publish child IDs or credentials.
2. Independently inspect the exact run using a read-only, owner-bound audit.
   Confirm `users.role=user`, `users.is_active=false`, the exact
   `finn_smart_dca_journey_qa_v1` marker and namespace, and the complete
   setup/strategy/bot lineage. Count exchange keys, bot portfolios, decisions,
   orders, executions, ledger and trade plans. A bot must be inactive.
3. Prepare a one-run cleanup path bound to that workflow run, attempt,
   namespace and previously audited row set. Require Security review, green
   CI, deployment identity and exact SHA parity before using it. Under the
   same owner lock, revalidate every expected row and zero trade/key/cash
   state. Unknown rows or changed ownership must abort without deletion.
4. After guarded cleanup, run a separate read-only audit proving
   `NO_RETAINED_FIXTURE`. Report both artifacts. Do not interpret a missing
   child as a successful functional journey.

The ordinary journey cleanup deliberately does not accept a previously
deactivated quarantined bot. Do not activate the child or bot, invoke the
Paper worker, add funds, or use a broad user-ID deletion to recover it.
