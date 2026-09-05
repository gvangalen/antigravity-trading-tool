const path = require("path");

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
  default: 2,
  marketPortfolio: 2,
  scoringExecution: 2,
  aiReporting: 1,
  finnInteractive: 2,
};

function pickRuntimeEnv(keys) {
  return keys.reduce((acc, key) => {
    if (typeof process.env[key] !== "undefined") {
      acc[key] = process.env[key];
    }
    return acc;
  }, {});
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
  "TRADAMIND_BUILD_COMMIT_SHA",
  "TRADAMIND_BUILD_TIME",
]);

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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
          ...SHARED_RUNTIME_ENV,
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
