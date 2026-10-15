# Uncertain live bot order recovery

`sending` and `unknown_exchange_state` block new live orders for the account.
They mean the exchange may have accepted an order even though its ID was not
saved locally. Never retry the original submission with a new idempotency key.

Use this procedure only from the backend runtime with its configured database
and exchange connection. Record the local user ID, order ID, bot, asset, side,
quantity, exchange, submission time, operator and incident ticket. Inspect the
account's exchange orders and fills around that time. Keep the account blocked
if the outcome is still uncertain.

After the `2026_10_15_bot_order_recovery_audit.py` migration is applied, run
the following from `backend/trading-tool-backend`:

```bash
python3 backend/scripts/recover_uncertain_bot_order.py \
  --user-id 123 --order-id 456 --action attach_exchange_order \
  --exchange-order-id EXCHANGE_ID --operator-id OPERATOR \
  --evidence-reference INCIDENT_TICKET \
  --confirmation 'I VERIFIED THIS EXCHANGE ORDER'
```

The script fetches that order using the account's active exchange connection,
checks ID, full EUR pair, side, quantity and limit price against the local order,
rejects an ID already linked to another order, saves the exchange
ID and an audit event atomically, then invokes fill reconciliation. If the
exchange cannot return or verify it, leave the order blocked and escalate.

Only if the exchange account has been checked and there is positive evidence
that **no order was created**, use:

```bash
python3 backend/scripts/recover_uncertain_bot_order.py \
  --user-id 123 --order-id 456 --action verified_no_order \
  --operator-id OPERATOR --evidence-reference INCIDENT_TICKET \
  --confirmation 'I VERIFIED NO EXCHANGE ORDER'
```

This marks the local order rejected and records the operator and evidence
reference. It does not submit or cancel an exchange order. Do not put API keys,
personal data or raw exchange exports in the evidence reference. Recheck the
bot and portfolio after recovery before allowing another live order.
