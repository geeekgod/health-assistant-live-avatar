# Nginx (production)

Domains:

| File | Domain | Proxies to |
|------|--------|------------|
| `sites-available/mykare-frontend` | `mykare.geeekgod.in` | `mykare_frontend` upstream |
| `sites-available/mykare-backend` | `mykare.backend.geeekgod.in` | `mykare_backend` upstream |
| `sites-available/mykare-livekit` | `mykare.livekit.geeekgod.in` | `127.0.0.1:7880` (self-hosted LiveKit) |

Blue-green upstream ports:

| Color | Frontend | Backend |
|-------|----------|---------|
| blue | 3000 | 8000 |
| green | 3002 | 8002 |

## One-time setup (on server)

```bash
cd /var/www/mykare-assessment/health-assistant-live-avatar

# 0. Open firewall (UFW + check DigitalOcean cloud firewall for 80/443)
sudo bash nginx/scripts/setup-firewall.sh

# 1. Install configs (HTTP only — required before certbot)
sudo bash nginx/scripts/install.sh blue

# 2. Verify HTTP
curl -I http://mykare.backend.geeekgod.in/health

# 3. Enable SSL
sudo bash nginx/scripts/enable-ssl.sh

# 4. Update docker/.env and redeploy
# NEXT_PUBLIC_API_URL=https://mykare.backend.geeekgod.in
# BACKEND_URL=https://mykare.backend.geeekgod.in
LIVEKIT=cloud bash docker/scripts/deploy.sh
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/doctor.sh` | Diagnose 502s (docker, ports, upstream mismatch) |
| `scripts/setup-firewall.sh` | Open UFW ports 22, 80, 443 (and LiveKit ports if needed) |
| `scripts/install.sh [blue\|green]` | Copy configs, symlink sites-enabled, set upstream |
| `scripts/enable-ssl.sh` | Certbot for all three domains |
| `scripts/update-upstream.sh [blue\|green]` | Switch upstream after blue-green deploy |
| `scripts/reload.sh` | `nginx -t` + reload |

`docker/scripts/deploy.sh` calls `update-upstream.sh` automatically after each deploy.

## Self-hosted LiveKit

When switching from LiveKit Cloud to local:

```env
LIVEKIT_URL=wss://mykare.livekit.geeekgod.in
LIVEKIT_INTERNAL_URL=ws://livekit:7880
```

```bash
LIVEKIT=local bash docker/scripts/deploy.sh
```

Open firewall: `7880/tcp`, `7881/tcp`, `50000:60000/udp`.

## Troubleshooting 502

502 = nginx works but **upstream is down or wrong port**.

```bash
bash nginx/scripts/doctor.sh
```

Common fixes:

1. **Docker not running** — deploy the stack:
   ```bash
   cd /var/www/mykare-assessment/health-assistant-live-avatar
   LIVEKIT=cloud bash docker/scripts/deploy.sh
   ```

2. **Upstream port mismatch** (blue-green) — sync nginx with active color:
   ```bash
   bash nginx/scripts/update-upstream.sh   # reads docker/.deploy-color
   ```

3. **LiveKit subdomain 502 with LiveKit Cloud** — nothing listens on `:7880`:
   ```bash
   sudo rm /etc/nginx/sites-enabled/mykare-livekit
   sudo nginx -t && sudo systemctl reload nginx
   ```

4. **Verify locally on server:**
   ```bash
   curl -I http://127.0.0.1:3000/api/health
   curl -I http://127.0.0.1:8000/health/ready
   docker ps
   ```
