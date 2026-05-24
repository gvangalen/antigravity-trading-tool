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
      name: 'celery-worker-default',
      script: '/home/ubuntu/.local/bin/celery',
      args: '-A backend.celery_task.celery_app worker --loglevel=info --concurrency=1 -Q celery -n default@%h',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      interpreter: 'none',
      max_memory_restart: '300M'
    },
    {
      name: 'celery-worker-market-portfolio',
      script: '/home/ubuntu/.local/bin/celery',
      args: '-A backend.celery_task.celery_app worker --loglevel=info --concurrency=1 -Q market_data,portfolio -n market-portfolio@%h',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      interpreter: 'none',
      max_memory_restart: '300M'
    },
    {
      name: 'celery-worker-scoring-execution',
      script: '/home/ubuntu/.local/bin/celery',
      args: '-A backend.celery_task.celery_app worker --loglevel=info --concurrency=1 -Q scoring,execution_critical -n scoring-execution@%h',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      interpreter: 'none',
      max_memory_restart: '300M'
    },
    {
      name: 'celery-worker-ai-reporting',
      script: '/home/ubuntu/.local/bin/celery',
      args: '-A backend.celery_task.celery_app worker --loglevel=info --concurrency=1 -Q ai_generation -n ai-reporting@%h',
      cwd: '/home/ubuntu/antigravity-trading-tool/backend/trading-tool-backend',
      interpreter: 'none',
      max_memory_restart: '350M'
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
