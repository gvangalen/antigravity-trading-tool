module.exports = {
  apps: [
    {
      name: 'frontend',
      script: 'npm',
      args: 'start',
      cwd: '/home/ubuntu/trading-tool-frontend',
      exec_mode: 'fork',
      interpreter: '/bin/bash', // ✅ Belangrijk!
      watch: false,
      env: {
        NODE_ENV: 'production',
        PORT: 3000,
      },
    },
  ],
};
