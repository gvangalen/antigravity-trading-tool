#cloud-config
package_update: true
package_upgrade: true

packages:
  - git
  - nginx
  - redis-server
  - postgresql
  - postgresql-contrib
  - python3-pip

write_files:
  - path: /etc/tradamind-environment
    permissions: "0644"
    content: |
      APP_ENV=${app_env}
      BACKEND_PORT=${backend_port}
      FRONTEND_PORT=${frontend_port}
      DEPLOY_ENVIRONMENT=${environment}

runcmd:
  - systemctl enable redis-server
  - systemctl start redis-server
  - systemctl enable postgresql
  - systemctl start postgresql
