#!/usr/bin/env node
/*
 * Post-deploy policy parity gate. It deliberately emits booleans only: the
 * protected environment remains the owner of the actual values and secrets.
 */
var childProcess = require("child_process");
var path = require("path");

var pm2Bin = process.env.PM2_BIN || path.join(
  process.env.HOME || "", ".nvm/versions/node/v20.19.5/bin/pm2"
);
var requiredApps = [
  "backend",
  "celery-worker-finn-interactive",
  "celery-worker-default",
  "celery-worker-market-portfolio",
  "celery-worker-scoring-execution",
  "celery-worker-ai-reporting"
];
var requiredPolicy = {
  FINN_V2_PROPOSALS_ENABLED: "true",
  FINN_V2_CONFIRMATIONS_ENABLED: "true",
  FINN_V2_WRITE_BLOCKED: "true",
  FINN_V2_LIVE_ACTIONS_ENABLED: "false",
  FINN_V2_PAPER_ACTIONS_ENABLED: "false",
  FINN_V2_EXECUTE_LIVE_BOT_ACTIVATION: "false",
  // These owner-scoped actions are still confirmation-gated by their action
  // contracts.  They must be enabled consistently in the API and workers so
  // a release cannot publish proposals that its execution worker always blocks.
  FINN_V2_EXECUTE_ASSET_SELECTION: "true",
  FINN_V2_EXECUTE_WATCHLIST_CHANGES: "true",
  FINN_V2_EXECUTE_INDICATOR_CHANGES: "true",
  FINN_V2_EXECUTE_SETUP_CHANGES: "true",
  FINN_V2_EXECUTE_STRATEGY_CHANGES: "true",
  FINN_V2_EXECUTE_BOT_CHANGES: "true",
  FINN_V2_EXECUTE_TRADE_PLAN_CHANGES: "false",
  FINN_V2_EXECUTE_PAPER_BOT_ACTIVATION: "false"
};

function processEnv(process) {
  return (process.pm2_env && process.pm2_env.env) || {};
}

function main() {
  var raw;
  try {
    raw = childProcess.execFileSync(pm2Bin, ["jlist"], { encoding: "utf8" });
  } catch (error) {
    console.log(JSON.stringify({ check: "finn_runtime_policy", pass: false, reason: "pm2_unavailable" }));
    process.exit(1);
  }
  var start = raw.indexOf("[");
  var apps;
  try {
    apps = JSON.parse(raw.slice(start));
  } catch (error) {
    console.log(JSON.stringify({ check: "finn_runtime_policy", pass: false, reason: "pm2_payload_invalid" }));
    process.exit(1);
  }
  var byName = {};
  apps.forEach(function (app) { byName[app.name] = app; });
  var missing = requiredApps.filter(function (name) { return !byName[name]; });
  var policyMatch = missing.length === 0 && requiredApps.every(function (name) {
    var env = processEnv(byName[name]);
    return Object.keys(requiredPolicy).every(function (key) { return env[key] === requiredPolicy[key]; });
  });
  var sha = process.env.TRADAMIND_BUILD_COMMIT_SHA || "";
  var shaMatch = sha.length > 0 && requiredApps.every(function (name) {
    return processEnv(byName[name]).TRADAMIND_BUILD_COMMIT_SHA === sha;
  });
  var pass = policyMatch && shaMatch;
  console.log(JSON.stringify({
    check: "finn_runtime_policy",
    pass: pass,
    api_worker_policy_parity: policyMatch,
    release_sha_parity: shaMatch,
    live_actions_disabled: policyMatch
  }));
  process.exit(pass ? 0 : 1);
}

main();
