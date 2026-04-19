#!/bin/bash

# ==============================================================================
# Tradamind SSL Setup Script
# Description: Automates Certbot SSL installation for Nginx.
# Target: Ubuntu/Debian Server
# Domains: tradamind.com, www.tradamind.com
# ==============================================================================

set -e

# Support for dynamic domain as argument
DOMAIN=${1:-"tradamind.com"}
echo "🚀 Starting SSL Setup for $DOMAIN..."

# 1. Check if Nginx is running
echo "🔍 Checking Nginx status..."
if ! systemctl is-active --quiet nginx; then
    echo "❌ Nginx is not running. Please start Nginx first."
    exit 1
fi
echo "✅ Nginx is running."

# 2. Install Certbot and Nginx plugin (if not already present)
echo "📦 Installing Certbot and python3-certbot-nginx..."
sudo apt update
sudo apt install certbot python3-certbot-nginx -y

# 3. Run Certbot
# --nginx: Use the Nginx plugin to automatically configure SSL
# --non-interactive: Don't ask for user input (requires email and agreement)
# --agree-tos: Agree to the Let's Encrypt Terms of Service
# --redirect: Automatically redirect HTTP traffic to HTTPS
echo "🔒 Requesting SSL certificate for $DOMAIN and www.$DOMAIN..."
# Note: You might need to provide an email address if it's the first time running certbot.
# If prompted, enter your email address for renewal reminders.
sudo certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --redirect

# 4. Verify auto-renewal
echo "⏰ Checking Certbot auto-renewal timer..."
sudo systemctl status certbot.timer

echo ""
echo "✅ SSL SETUP COMPLETE"
echo "--------------------------------------------------"
echo "Website: https://www.$DOMAIN"
echo "API:     https://www.$DOMAIN/api"
echo "--------------------------------------------------"
echo "To switch domains later, just run this script again with the new name:"
echo "Example: ./setup_ssl.sh newdomain.com"
