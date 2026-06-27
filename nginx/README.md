# Nginx (production)

Domains:

| File | Domain | Proxies to |
|------|--------|------------|
| `sites-available/mykare-frontend` | `mykare.geeekgod.in` | `mykare_frontend` upstream |
| `sites-available/mykare-backend` | `mykare.backend.geeekgod.in` | `mykare_backend` upstream |
| `sites-available/mykare-livekit` | `mykare.livekit.geeekgod.in` | `127.0.0.1:7880` (self-hosted LiveKit only) |

Blue-green upstream ports:

| Color | Frontend | Backend |
|-------|----------|---------|
| blue | 3000 | 8000 |
| green | 3002 | 8002 |

`install.sh` and `enable-ssl.sh` read **LiveKit mode** from `LIVEKIT` env or `docker/.env`:
- **cloud / off** — frontend + backend sites only (no livekit subdomain)
- **local** — all three sites + LiveKit firewall ports

## One-time setup (on server)

```bash
cd /var/www/mykare-assessment/health-assistant-live-avatar
git pull

# 1. Deploy app (HTTP must work before certbot)
LIVEKIT=cloud bash docker/scripts/deploy.sh

# 2. Install nginx (auto-picks blue/green from docker/.deploy-color)
sudo bash nginx/scripts/install.sh

# 3. Verify HTTP
curl -I http://mykare.backend.geeekgod.in/health/ready

# 4. Enable SSL (opens UFW, certbot, patches docker/.env)
sudo CERTBOT_EMAIL=you@example.com bash nginx/scripts/enable-ssl.sh

# 5. Redeploy so frontend rebuilds with HTTPS API URL
LIVEKIT=cloud bash docker/scripts/deploy.sh
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/lib.sh` | Shared helpers (LiveKit mode, HTTPS env patch) |
| `scripts/doctor.sh` | Diagnose 502s, SSL, upstream mismatch |
| `scripts/setup-firewall.sh` | Open UFW 22/80/443 (+ LiveKit if local) |
| `scripts/install.sh [blue\|green]` | Copy configs; skip livekit site when cloud |
| `scripts/enable-ssl.sh` | Firewall + certbot + patch `docker/.env` |
| `scripts/update-upstream.sh [blue\|green]` | Switch upstream after blue-green deploy |
| `scripts/reload.sh` | `nginx -t` + reload |

`docker/scripts/deploy.sh` calls `update-upstream.sh` automatically and warns if SSL/env are out of sync.

## Self-hosted LiveKit

```env
LIVEKIT_URL=wss://mykare.livekit.geeekgod.in
LIVEKIT_INTERNAL_URL=ws://livekit:7880
```

```bash
LIVEKIT=local bash docker/scripts/deploy.sh
sudo bash nginx/scripts/install.sh
sudo bash nginx/scripts/enable-ssl.sh
```

## Troubleshooting

```bash
bash nginx/scripts/doctor.sh
```

| Symptom | Fix |
|---------|-----|
| 502 on frontend/backend | `LIVEKIT=cloud bash docker/scripts/deploy.sh` |
| Wrong upstream port | `bash nginx/scripts/update-upstream.sh` |
| 502 on livekit subdomain (cloud) | `sudo bash nginx/scripts/install.sh` (disables livekit site) |
| HTTP works, HTTPS doesn't | `sudo bash nginx/scripts/enable-ssl.sh` |
| HTTPS works, API calls fail | `.env` still `http://` — run `enable-ssl.sh` + redeploy |
| Certbot timeout | Open TCP 80/443 in UFW + cloud firewall |
