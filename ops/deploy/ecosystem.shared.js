const path = require("path");
const fs = require("fs");
const os = require("os");

function positiveIntEnv(name, fallback) {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isInteger(value) || value < 1 || value > 128) {
    throw new Error(`${name} must be an integer between 1 and 128`);
  }
  return value;
}

const capacityProfile = require("./capacity_profile.json");
const WORKER_TOPOLOGY = process.env.TRADAMIND_WORKER_TOPOLOGY || capacityProfile.topology;
if (!["compact", "scaled"].includes(WORKER_TOPOLOGY)) {
  throw new Error("TRADAMIND_WORKER_TOPOLOGY must be compact or scaled");
}
const SCALED = WORKER_TOPOLOGY === "scaled";
if (SCALED && os.totalmem() < 6 * 1024 ** 3) {
  throw new Error("Scaled worker topology requires at least 6 GiB host RAM");
}
const API_WORKERS = positiveIntEnv("API_WORKERS", SCALED ? 2 : 1);

const BASE_REMOTE_DIR = process.env.REMOTE_DIR || "/home/ubuntu/antigravity-trading-tool";
const NODE_INTERPRETER =
  process.env.NODE_INTERPRETER || "/home/ubuntu/.nvm/versions/node/v20.19.5/bin/node";
const CELERY_BIN = process.env.CELERY_BIN || "/home/ubuntu/.local/bin/celery";

const ENVIRONMENTS = {
  production: {
    suffix: "",
    appEnv: "production",
    frontendPort: 5002,
    backendPort: 8000,
    queueNamePrefix: "",
  },
  staging: {
    suffix: "-staging",
    appEnv: "staging",
    frontendPort: 5102,
    backendPort: 8100,
    queueNamePrefix: "staging-",
  },
};

const WORKER_CONCURRENCY = {
  // An earlier 1 GB production host could not sustain four separate
  // background prefork process trees plus FINN's dedicated queue: the kernel
  // killed workers under sustained interactive traffic. Measure the current
  // host before selecting a larger topology. In compact mode, keep FINN
  // isolated and serve the other queues from one bounded shared worker.
  background: 1,
  finnInteractive: 1,
  marketPortfolio: positiveIntEnv("CELERY_MARKET_PORTFOLIO_CONCURRENCY", 2),
  scoring: positiveIntEnv("CELERY_SCORING_CONCURRENCY", 1),
  executionCritical: positiveIntEnv("CELERY_EXECUTION_CONCURRENCY", 1),
  aiReporting: positiveIntEnv("CELERY_AI_REPORTING_CONCURRENCY", 2),
  scaledFinnInteractive: positiveIntEnv("CELERY_FINN_INTERACTIVE_CONCURRENCY", 2),
};

const apiDbMaximum = 23;
const backgroundDbMaximum = 4;
const finnDbMaximum = 3;
const workerDbMaximum = SCALED
  ? backgroundDbMaximum * (WORKER_CONCURRENCY.background + WORKER_CONCURRENCY.marketPortfolio
      + WORKER_CONCURRENCY.scoring + WORKER_CONCURRENCY.executionCritical + WORKER_CONCURRENCY.aiReporting)
    + finnDbMaximum * WORKER_CONCURRENCY.scaledFinnInteractive
  : backgroundDbMaximum + finnDbMaximum;
const dbConnectionBudget = positiveIntEnv("DB_CONNECTION_BUDGET", 80);
const configuredDbMaximum = API_WORKERS * apiDbMaximum + workerDbMaximum;
if (configuredDbMaximum > dbConnectionBudget) {
  throw new Error(`Configured DB connection maximum ${configuredDbMaximum} exceeds budget ${dbConnectionBudget}`);
}

function pickRuntimeEnv(keys) {
  return keys.reduce((acc, key) => {
    if (typeof process.env[key] !== "undefined") {
      acc[key] = process.env[key];
    }
    return acc;
  }, {});
}

function loadReleaseMetadata() {
  const metadataPath = path.join(BASE_REMOTE_DIR, "ops", "deploy", ".release_metadata.env");
  try {
    return fs.readFileSync(metadataPath, "utf8").split("\n").reduce((metadata, line) => {
      const match = /^(TRADAMIND_BUILD_COMMIT_SHA|TRADAMIND_BUILD_TIME)=([^\n]+)$/.exec(line);
      if (match) {
        metadata[match[1]] = match[2];
      }
      return metadata;
    }, {});
  } catch (error) {
    return {};
  }
}

const SHARED_RUNTIME_ENV = pickRuntimeEnv([
  "TWELVE_DATA_API_KEY",
  "OPENAI_API_KEY",
  "OPENAI_CALLS_ENABLED",
  "FRONTEND_URL",
  "CORS_ORIGINS",
  "CORS_ALLOW_ORIGIN_REGEX",
  "DATABASE_URL",
  "SECRET_KEY",
  "JWT_SECRET_KEY",
  "JWT_ALGORITHM",
  "ACCESS_TOKEN_EXPIRE_MINUTES",
  "REFRESH_TOKEN_EXPIRE_DAYS",
  "FRED_API_KEY",
  "ALPHA_VANTAGE_API_KEY",
  "COINMARKETCAP_API_KEY",
  "BINANCE_API_KEY",
  "BINANCE_API_SECRET",
  "BYBIT_API_KEY",
  "BYBIT_API_SECRET",
  "COINBASE_API_KEY",
  "COINBASE_API_SECRET",
  "REDIS_URL",
  "TRUSTED_PROXY_CIDRS",
  "CELERY_BROKER_URL",
  "CELERY_RESULT_BACKEND",
  // FINN's runtime safety policy is configured by the protected server
  // environment.  Forward every supported FINN V2 switch to both the API and
  // all Celery workers so a proposal cannot be evaluated under one policy and
  // executed under another after a PM2 restart.
  "FINN_V2_ENABLED",
  "FINN_V2_VISIBLE_ENABLED",
  "FINN_V2_WRITE_BLOCKED",
  "FINN_V2_MAX_EXECUTES_PER_MINUTE",
  "FINN_V2_ALLOWED_TRANSPORTS",
  "FINN_V2_ORCHESTRATOR_ENABLED",
  "FINN_V2_POLICY_ENGINE_ENABLED",
  "FINN_V2_PROPOSALS_ENABLED",
  "FINN_V2_VISIBLE_PROPOSALS_ENABLED",
  "FINN_V2_CONFIRMATIONS_ENABLED",
  "FINN_V2_CONFIRMATION_ROUTES_ENABLED",
  "FINN_V2_ACTION_EXECUTION_ENABLED",
  "FINN_V2_EXECUTION_GATE_ENABLED",
  "FINN_V2_ACTION_KILL_SWITCH",
  "FINN_V2_LIVE_ACTIONS_ENABLED",
  "FINN_V2_PAPER_ACTIONS_ENABLED",
  "FINN_V2_EXECUTE_ASSET_SELECTION",
  "FINN_V2_EXECUTE_WATCHLIST_CHANGES",
  "FINN_V2_EXECUTE_INDICATOR_CHANGES",
  "FINN_V2_EXECUTE_SETUP_CHANGES",
  "FINN_V2_EXECUTE_STRATEGY_CHANGES",
  "FINN_V2_EXECUTE_BOT_CHANGES",
  "FINN_V2_EXECUTE_TRADE_PLAN_CHANGES",
  "FINN_V2_EXECUTE_PAPER_BOT_ACTIVATION",
  "FINN_V2_EXECUTE_LIVE_BOT_ACTIVATION",
  "FINN_TRADE_REVIEW_ROLLOUT",
  "FINN_TRADE_REVIEW_USER_IDS",
  "FINN_V2_LIFECYCLE_DEADLINE_SECONDS",
  "FINN_V2_SELECTOR_PHASE_DEADLINE_SECONDS",
  "FINN_V2_REASONING_TIMEOUT_SECONDS",
  "FINN_V2_RESPONSES_LIFECYCLE_DEADLINE_SECONDS",
  "FINN_MINIMAL_READ_ANSWERS",
  "TRADAMIND_BUILD_COMMIT_SHA",
  "TRADAMIND_BUILD_TIME",
]);

// PM2's --update-env merges with an existing process environment.  Define the
// safe FINN defaults explicitly so an obsolete process-only false value cannot
// survive a release when the protected environment deliberately omits a key.
// A protected value in SHARED_RUNTIME_ENV always takes precedence.
const FINN_RUNTIME_DEFAULT_ENV = {
  // A missing protected rollout setting must also clear a stale PM2 value.
  FINN_TRADE_REVIEW_ROLLOUT: "off",
  FINN_TRADE_REVIEW_USER_IDS: "",
  // Pin the default Responses route across the API and workers. PM2 merges
  // process environment on --update-env, so code defaults alone cannot
  // replace a stale model value from an earlier release.
  FINN_RESPONSES_CHAT_MODEL: "gpt-6-luna",
  FINN_RESPONSES_CLARIFICATION_MODEL: "gpt-6-luna",
  FINN_RESPONSES_REPAIR_MODEL: "gpt-6-luna",
  FINN_RESPONSES_REASONING_EFFORT: "none",
  FINN_V2_RESPONSES_LIFECYCLE_DEADLINE_SECONDS: "40",
  FINN_MINIMAL_READ_ANSWERS: "1",
  FINN_V2_PROPOSALS_ENABLED: "true",
  FINN_V2_VISIBLE_PROPOSALS_ENABLED: "true",
  FINN_V2_CONFIRMATIONS_ENABLED: "true",
  FINN_V2_CONFIRMATION_ROUTES_ENABLED: "true",
  FINN_V2_ACTION_EXECUTION_ENABLED: "true",
  FINN_V2_EXECUTION_GATE_ENABLED: "true",
  FINN_V2_WRITE_BLOCKED: "true",
  FINN_V2_ACTION_KILL_SWITCH: "true",
  // These actions mutate only owner-scoped FINN configuration records and all
  // still require the existing proposal, confirmation and execution gates.
  // They are distinct from financial order placement and live bot activation.
  FINN_V2_EXECUTE_ASSET_SELECTION: "true",
  FINN_V2_EXECUTE_WATCHLIST_CHANGES: "true",
  FINN_V2_EXECUTE_INDICATOR_CHANGES: "true",
  FINN_V2_EXECUTE_SETUP_CHANGES: "true",
  FINN_V2_EXECUTE_STRATEGY_CHANGES: "true",
  FINN_V2_EXECUTE_BOT_CHANGES: "true",
  FINN_V2_EXECUTE_TRADE_PLAN_CHANGES: "false",
  FINN_V2_EXECUTE_PAPER_BOT_ACTIVATION: "false",
  FINN_V2_LIVE_ACTIONS_ENABLED: "false",
  FINN_V2_PAPER_ACTIONS_ENABLED: "false",
  FINN_V2_EXECUTE_LIVE_BOT_ACTIVATION: "false",
};
const RELEASE_METADATA_ENV = loadReleaseMetadata();

function createEcosystem(environmentName) {
  const environment = ENVIRONMENTS[environmentName];
  if (!environment) {
    throw new Error(`Unknown ecosystem environment: ${environmentName}`);
  }
  // Closed-trade reflection is a product feature for every production owner.
  // Override stale protected allowlists and PM2 process state on deployment.
  const backendRuntimeEnv = environmentName === "production"
    ? { ...SHARED_RUNTIME_ENV, FINN_TRADE_REVIEW_ROLLOUT: "all", FINN_TRADE_REVIEW_USER_IDS: "" }
    : SHARED_RUNTIME_ENV;

  const projectDir = BASE_REMOTE_DIR;
  const frontendDir = path.join(projectDir, "frontend", "trading-tool-frontend");
  const backendDir = path.join(projectDir, "backend", "trading-tool-backend");
  const backendApp = `backend${environment.suffix}`;
  const frontendApp = `frontend${environment.suffix}`;
  const backgroundWorker = `celery-worker-default${environment.suffix}`;
  const finnInteractiveWorker = `celery-worker-finn-interactive${environment.suffix}`;
  const beatWorker = `celery-beat${environment.suffix}`;
  const queuePrefix = environment.queueNamePrefix;

  const workerApp = (name, workerName, queues, pool, concurrency, profile, memoryLimit) => ({
    name,
    script: CELERY_BIN,
    args: `-A backend.celery_task.celery_app worker --pool=${pool} --loglevel=info -Ofair --concurrency=${concurrency} -Q ${queues.map((queue) => `${queuePrefix}${queue}`).join(",")} -n ${environmentName}-${workerName}@%h`,
    cwd: backendDir,
    interpreter: "none",
    env: {
      ...FINN_RUNTIME_DEFAULT_ENV,
      ...backendRuntimeEnv,
      ...RELEASE_METADATA_ENV,
      APP_ENV: environment.appEnv,
      TRADAMIND_BUILD_SERVICE: name.replace(environment.suffix, ""),
      TRADAMIND_CELERY_PROFILE: profile,
    },
    max_memory_restart: memoryLimit,
  });

  return {
    apps: [
      {
        name: frontendApp,
        script: "server.js",
        cwd: frontendDir,
        interpreter: NODE_INTERPRETER,
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          NODE_ENV: "production",
          PORT: environment.frontendPort,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "frontend",
        },
        max_memory_restart: "500M",
      },
      {
        name: backendApp,
        script: "python3",
        args: `-m uvicorn backend.main:app --host 0.0.0.0 --port ${environment.backendPort} --workers ${API_WORKERS}`,
        cwd: backendDir,
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...backendRuntimeEnv,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "backend",
          TRADAMIND_CELERY_PROFILE: "api",
        },
        max_memory_restart: "500M",
      },
      workerApp(
        backgroundWorker, "background", SCALED ? ["celery"]
          : ["celery", "market_data", "portfolio", "scoring", "execution_critical", "ai_generation"],
        "solo", WORKER_CONCURRENCY.background, "full", "300M",
      ),
      ...(SCALED ? [
        workerApp(`celery-worker-market-portfolio${environment.suffix}`, "market-portfolio",
          ["market_data", "portfolio"], "prefork", WORKER_CONCURRENCY.marketPortfolio, "full", "900M"),
        workerApp(`celery-worker-scoring${environment.suffix}`, "scoring",
          ["scoring"], "solo", WORKER_CONCURRENCY.scoring, "full", "500M"),
        workerApp(`celery-worker-execution-critical${environment.suffix}`, "execution-critical",
          ["execution_critical"], "solo", WORKER_CONCURRENCY.executionCritical, "full", "500M"),
        workerApp(`celery-worker-ai-reporting${environment.suffix}`, "ai-reporting",
          ["ai_generation"], "prefork", WORKER_CONCURRENCY.aiReporting, "full", "900M"),
      ] : []),
      workerApp(finnInteractiveWorker, "finn-interactive", ["finn_interactive"],
        SCALED ? "prefork" : "solo",
        SCALED ? WORKER_CONCURRENCY.scaledFinnInteractive : WORKER_CONCURRENCY.finnInteractive,
        "finn", SCALED ? "900M" : "350M"),
      {
        name: beatWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app beat --loglevel=info --pidfile=/tmp/tradamind-${environmentName}-celery-beat.pid`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...backendRuntimeEnv,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-beat",
          TRADAMIND_CELERY_PROFILE: "api",
        },
        max_memory_restart: "200M",
      },
    ],
  };
}

module.exports = {
  createEcosystem,
  ENVIRONMENTS,
  WORKER_CONCURRENCY,
  WORKER_TOPOLOGY,
  API_WORKERS,
  configuredDbMaximum,
};
