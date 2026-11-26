import assert from "node:assert/strict";
import test from "node:test";

import { dcaBotPlan, dcaBotBudgetCheck, dcaPurchaseCapacity } from "../lib/bot/dcaBotPlan.mjs";

const setup = { setup_type: "dca", dca_frequency: "weekly", dca_day: "1" };

test("fixed weekly DCA takes its purchase amount from the strategy, not the bot budget", () => {
  const plan = dcaBotPlan({ execution_mode: "fixed", base_amount: 10 }, setup);
  assert.deepEqual(plan, { minimum: 10, maximum: 10, base: 10, variable: false });
  assert.equal(dcaPurchaseCapacity(plan, 200), 20);
  assert.equal(dcaPurchaseCapacity(plan, ""), null);
  assert.equal(dcaBotBudgetCheck(plan, { budget_total_eur: 0 }), "total");
  assert.equal(dcaBotPlan({ execution_mode: "fixed", base_amount: 10 }, { setup_type: "trade" }), null);
});

test("score-banded DCA checks the entire saved amount range and Paper funding", () => {
  const plan = dcaBotPlan({
    execution_mode: "custom", base_amount: 20,
    decision_curve: { points: [{ y: 0.5 }, { y: 1 }, { y: 2 }] },
  }, setup);
  assert.deepEqual(plan, { minimum: 10, maximum: 40, base: 20, variable: true });
  const values = {
    budget_total_eur: 200, budget_daily_limit_eur: 40,
    budget_min_order_eur: 10, budget_max_order_eur: 40,
    paper_initial_cash_eur: 40,
  };
  const options = { automatic: true, paper: true, create: true };
  assert.equal(dcaBotBudgetCheck(plan, values, options), null);
  assert.equal(dcaBotBudgetCheck(plan, { ...values, budget_daily_limit_eur: 20 }, options), "daily");
  assert.equal(dcaBotBudgetCheck(plan, { ...values, budget_max_order_eur: 20 }, options), "maximum");
  assert.equal(dcaBotBudgetCheck(plan, { ...values, budget_min_order_eur: 20 }, options), "minimum");
  assert.equal(dcaBotBudgetCheck(plan, { ...values, paper_initial_cash_eur: 20 }, options), "cash");
});
