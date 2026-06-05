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
};

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
          NODE_ENV: "production",
          PORT: environment.frontendPort,
          APP_ENV: environment.appEnv,
        },
        max_memory_restart: "500M",
      },
      {
        name: backendApp,
        script: "python3",
        args: `-m uvicorn backend.main:app --host 0.0.0.0 --port ${environment.backendPort}`,
        cwd: backendDir,
        env: {
          APP_ENV: environment.appEnv,
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
          APP_ENV: environment.appEnv,
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
          APP_ENV: environment.appEnv,
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
          APP_ENV: environment.appEnv,
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
          APP_ENV: environment.appEnv,
        },
        max_memory_restart: "350M",
      },
      {
        name: beatWorker,
        script: CELERY_BIN,
        args: "-A backend.celery_task.celery_app beat --loglevel=info",
        cwd: backendDir,
        interpreter: "none",
        env: {
          APP_ENV: environment.appEnv,
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
