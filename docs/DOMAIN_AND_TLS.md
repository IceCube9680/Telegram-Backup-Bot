# Domain, DNS & TLS/HTTPS Production Guide

This document explains the production domain configuration, DNS records, TLS certificate provisioning via Let's Encrypt (Certbot), reverse proxy configuration, and certificate auto-renewal for the **Telegram Backup Bot**.

---

## 1. Architecture Overview

```text
                  Public Internet
                         │
                         ▼
              ┌─────────────────────┐
              │  DNS A/AAAA Record  │
              │  backup.example.com │
              └──────────┬──────────┘
                         │
                         ▼
           ┌───────────────────────────┐
           │   VPS Host / Server       │
           │   Public IP: 198.51.100.1 │
           │                           │
           │   ┌───────────────────┐   │
           │   │    Nginx :443     │   │
           │   │   (TLS / HTTPS)   │   │
           │   └─────────┬─────────┘   │
           │             │             │
           │      127.0.0.1:8000       │
           │             │             │
           │   ┌─────────▼─────────┐   │
           │   │  FastAPI Backend  │   │
           │   │  (Docker network) │   │
           │   └───────────────────┘   │
           └───────────────────────────┘
```

---

## 2. DNS Configuration

Add the following DNS records at your domain registrar / DNS provider (Cloudflare, Route53, Namecheap, etc.):

| Type | Name / Host | Value / Target | TTL | Description |
| :--- | :--- | :--- | :--- | :--- |
| **A** | `backup` (or `@`) | `<YOUR_SERVER_IPV4_ADDRESS>` | 300 / Auto | IPv4 address of production VPS |
| **AAAA** | `backup` (or `@`) | `<YOUR_SERVER_IPV6_ADDRESS>` | 300 / Auto | (Optional) IPv6 address of VPS |

### Verifying DNS Propagation

Before provisioning TLS certificates, verify that DNS has propagated globally:

```bash
# Check DNS resolution
dig +short backup.example.com

# Or using nslookup
nslookup backup.example.com
```

---

## 3. Firewall & Port Requirements

Open ports `80` (HTTP) and `443` (HTTPS) on your firewall (UFW, AWS Security Group, Hetzner Firewall, etc.):

```bash
# Ubuntu/Debian UFW example
sudo ufw allow 80/tcp comment "HTTP (Let's Encrypt challenge & redirect)"
sudo ufw allow 443/tcp comment "HTTPS (TLS encrypted traffic)"
sudo ufw reload
```

> [!CAUTION]
> **DO NOT** open port `27017` (MongoDB) to the public internet. MongoDB is strictly bound to Docker's internal bridge network.

---

## 4. Let's Encrypt TLS Certificate Issuance (Certbot)

### Method A: Standalone / Webroot with Certbot (Recommended)

1. **Install Certbot**:
   ```bash
   sudo apt-get update
   sudo apt-get install -y certbot python3-certbot-nginx
   ```

2. **Obtain Certificate**:
   ```bash
   sudo certbot certonly --webroot \
     -w /var/www/certbot \
     -d backup.example.com \
     --agree-tos \
     --email admin@example.com \
     --non-interactive
   ```

   Certificates will be saved to:
   - Full chain: `/etc/letsencrypt/live/backup.example.com/fullchain.pem`
   - Private key: `/etc/letsencrypt/live/backup.example.com/privkey.pem`

---

## 5. Nginx Production Configuration

Review `deploy/nginx/nginx.conf`:

```nginx
# 1. HTTP Server — Automatic Redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name backup.example.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# 2. HTTPS Server — TLS Termination & Proxying
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name backup.example.com;

    ssl_certificate /etc/letsencrypt/live/backup.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/backup.example.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Request-ID $http_x_request_id;
        proxy_buffering off;
    }
}
```

---

## 6. Certificate Auto-Renewal & Testing

Let's Encrypt certificates are valid for 90 days. Certbot automatically configures a systemd timer for renewals.

### Test Certificate Renewal (Dry Run)

```bash
sudo certbot renew --dry-run
```

### Automatic Post-Renewal Nginx Reload Hook

Add a deploy hook in `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`:

```bash
#!/usr/bin/env bash
systemctl reload nginx || docker compose -f /path/to/docker-compose.prod.yml exec nginx nginx -s reload
```

Make it executable:
```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## 7. Local & Staging Testing (Without a Public Domain)

When developing or validating on localhost / staging without a public domain:

1. Use self-signed certificates or test directly over HTTP on `http://127.0.0.1:8000`.
2. Generate local self-signed TLS certificates for development:
   ```bash
   mkdir -p deploy/nginx/certs
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout deploy/nginx/certs/dev.key \
     -out deploy/nginx/certs/dev.crt \
     -subj "/CN=localhost"
   ```
3. Set `WEB_COOKIE_SECURE=false` in `.env` if testing web login on plain HTTP.
