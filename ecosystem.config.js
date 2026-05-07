module.exports = {
  apps: [
    {
      name: 'frontend',
      script: 'server.js',
      cwd: '/home/ubuntu/antigravity-trading-tool/frontend/trading-tool-frontend',
      interpreter: '/home/ubuntu/.nvm/versions/node/v20.19.5/bin/node',
      env: {
        NODE_ENV: 'production',
        PORT: 5002
      },
      max_memory_restart: '500M'
    },
    {
      name: 'backend',
      script: 'python3',
      args: '-m uvicorn backend.main:app --host 0.0.0.0 --port 8000',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      max_memory_restart: '500M'
    },
    {
      name: 'celery-worker',
      script: '/home/ubuntu/.local/bin/celery',
      args: '-A backend.celery_task.celery_app worker --loglevel=info --concurrency=1',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      interpreter: 'none',
      max_memory_restart: '300M'
    },
    {
      name: 'celery-beat',
      script: '/home/ubuntu/.local/bin/celery',
      args: '-A backend.celery_task.celery_app beat --loglevel=info',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      interpreter: 'none',
      max_memory_restart: '200M'
    }
  ]
};
