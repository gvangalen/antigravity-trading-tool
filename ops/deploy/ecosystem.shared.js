const path = require("path");
const fs = require("fs");

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
  // The production host has 1 GB RAM. Five prefork workers at concurrency 2
  // cold-start into swap, delaying the user-facing FINN queue for minutes.
  // One child per isolated queue keeps every workload serviceable without
  // turning a deployment into a memory-contention event.
  default: 1,
  marketPortfolio: 1,
  scoringExecution: 1,
  aiReporting: 1,
  finnInteractive: 1,
};

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
  "FINN_V2_LIFECYCLE_DEADLINE_SECONDS",
  "FINN_V2_SELECTOR_PHASE_DEADLINE_SECONDS",
  "FINN_V2_REASONING_TIMEOUT_SECONDS",
  "TRADAMIND_BUILD_COMMIT_SHA",
  "TRADAMIND_BUILD_TIME",
]);
// PM2's --update-env merges with an existing process environment.  Define the
// safe FINN defaults explicitly so an obsolete process-only false value cannot
// survive a release when the protected environment deliberately omits a key.
// A protected value in SHARED_RUNTIME_ENV always takes precedence.
const FINN_RUNTIME_DEFAULT_ENV = {
  FINN_V2_PROPOSALS_ENABLED: "true",
  FINN_V2_VISIBLE_PROPOSALS_ENABLED: "true",
  FINN_V2_CONFIRMATIONS_ENABLED: "true",
  FINN_V2_CONFIRMATION_ROUTES_ENABLED: "true",
  FINN_V2_ACTION_EXECUTION_ENABLED: "true",
  FINN_V2_EXECUTION_GATE_ENABLED: "true",
  FINN_V2_WRITE_BLOCKED: "true",
  FINN_V2_ACTION_KILL_SWITCH: "true",
  FINN_V2_LIVE_ACTIONS_ENABLED: "false",
  FINN_V2_PAPER_ACTIONS_ENABLED: "false",
};
const RELEASE_METADATA_ENV = loadReleaseMetadata();

function createEcosystem(environmentName) {
  const environment = ENVIRONMENTS[environmentName];
  if (!environment) {
    throw new Error(`Unknown ecosystem environment: ${environmentName}`);
  }

  const projectDir = BASE_REMOTE_DIR;
  const frontendDir = path.join(projectDir, "frontend", "trading-tool-frontend");
  const backendDir = path.join(projectDir, "backend", "trading-tool-backend");
  const backendApp = `backend${environment.suffix}`;
  const frontendApp = `frontend${environment.suffix}`;
  const defaultWorker = `celery-worker-default${environment.suffix}`;
  const marketPortfolioWorker = `celery-worker-market-portfolio${environment.suffix}`;
  const scoringExecutionWorker = `celery-worker-scoring-execution${environment.suffix}`;
  const aiReportingWorker = `celery-worker-ai-reporting${environment.suffix}`;
  const finnInteractiveWorker = `celery-worker-finn-interactive${environment.suffix}`;
  const beatWorker = `celery-beat${environment.suffix}`;
  const queuePrefix = environment.queueNamePrefix;

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
        args: `-m uvicorn backend.main:app --host 0.0.0.0 --port ${environment.backendPort}`,
        cwd: backendDir,
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "backend",
        },
        max_memory_restart: "500M",
      },
      {
        name: defaultWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY.default} -Q ${queuePrefix}celery -n ${environmentName}-default@%h`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-worker-default",
        },
        max_memory_restart: "300M",
      },
      {
        name: marketPortfolioWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY.marketPortfolio} -Q ${queuePrefix}market_data,${queuePrefix}portfolio -n ${environmentName}-market-portfolio@%h`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-worker-market-portfolio",
        },
        max_memory_restart: "300M",
      },
      {
        name: scoringExecutionWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY.scoringExecution} -Q ${queuePrefix}scoring,${queuePrefix}execution_critical -n ${environmentName}-scoring-execution@%h`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-worker-scoring-execution",
        },
        max_memory_restart: "300M",
      },
      {
        name: aiReportingWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY.aiReporting} -Q ${queuePrefix}ai_generation -n ${environmentName}-ai-reporting@%h`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-worker-ai-reporting",
        },
        max_memory_restart: "350M",
      },
      {
        name: finnInteractiveWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app worker --loglevel=info -Ofair --concurrency=${WORKER_CONCURRENCY.finnInteractive} --max-tasks-per-child=50 -Q ${queuePrefix}finn_interactive -n ${environmentName}-finn-interactive@%h`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-worker-finn-interactive",
        },
        max_memory_restart: "350M",
      },
      {
        name: beatWorker,
        script: CELERY_BIN,
        args: `-A backend.celery_task.celery_app beat --loglevel=info --pidfile=/tmp/tradamind-${environmentName}-celery-beat.pid`,
        cwd: backendDir,
        interpreter: "none",
        env: {
          ...FINN_RUNTIME_DEFAULT_ENV,
          ...SHARED_RUNTIME_ENV,
          ...RELEASE_METADATA_ENV,
          APP_ENV: environment.appEnv,
          TRADAMIND_BUILD_SERVICE: "celery-beat",
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
};
