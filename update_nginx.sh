#!/bin/bash
# ==================================================================
# 🚀 NGINX PORT SYNC SCRIPT (Frontend 5002, Backend 8000)
# ==================================================================
# Run with: sudo bash update_nginx.sh
# ==================================================================

set -e

NGINX_CONF="/etc/nginx/sites-available/default"
DOMAIN="tradamind.com"
WWW_DOMAIN="www.tradamind.com"

echo "🔧 Generating Nginx configuration for $DOMAIN..."

cat <<EOF > /tmp/nginx_config
server {
    listen 80;
    server_name $DOMAIN $WWW_DOMAIN;
    
    # Redirect all HTTP traffic to HTTPS
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name $DOMAIN $WWW_DOMAIN;

    # SSL Certificates (managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # 💻 FRONTEND (Static pre-built via PM2 on port 5002)
    location / {
        proxy_pass http://127.0.0.1:5002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }

    # 🔧 BACKEND (FastAPI API on port 8000)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        
        # Timeout settings for long AI requests
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }
}
EOF

echo "📝 Applying configuration to $NGINX_CONF..."
sudo cp /tmp/nginx_config "$NGINX_CONF"

echo "🧪 Testing Nginx configuration..."
sudo nginx -t

echo "♻️ Restarting Nginx..."
sudo systemctl restart nginx

echo "✅ Nginx is now synchronized!"
echo "Frontend: 5002"
echo "Backend:  8000"
