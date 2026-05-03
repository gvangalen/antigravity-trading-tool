module.exports = {
  apps: [
    {
      name: 'frontend',
      script: 'server.js',
      cwd: './frontend/trading-tool-frontend',
      env: {
        NODE_ENV: 'production',
        PORT: 5008
      },
      max_memory_restart: '500M'
    },
    {
      name: 'backend',
      script: 'python3',
      args: '-m uvicorn backend.main:app --host 0.0.0.0 --port 8000',
      cwd: './backend/trading-tool-backend',
      max_memory_restart: '500M'
    },
    {
      name: 'celery-worker',
      script: 'celery',
      args: '-A backend.celery_task.celery_app worker --loglevel=info --concurrency=1',
      cwd: './backend/trading-tool-backend',
      max_memory_restart: '300M'
    },
    {
      name: 'celery-beat',
      script: 'celery',
      args: '-A backend.celery_task.celery_app beat --loglevel=info',
      cwd: './backend/trading-tool-backend',
      max_memory_restart: '200M'
    }
  ]
};
