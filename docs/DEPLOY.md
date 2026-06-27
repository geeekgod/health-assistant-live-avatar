# GitHub Actions deployment setup

Deploys to `/var/www/mykare-assessment/health-assistant-live-avatar` on push to `main`.

## Workflows

| File                           | Trigger                   | What it does                                  |
| ------------------------------ | ------------------------- | --------------------------------------------- |
| `.github/workflows/deploy.yml` | Push to `main`, or manual | SSH → `git pull` → `docker/scripts/deploy.sh` |

## One-time server setup

```bash
# On the server (as your deploy user)
sudo mkdir -p /var/www/mykare-assessment
sudo chown "$USER:$USER" /var/www/mykare-assessment

cd /var/www/mykare-assessment
git clone <your-repo-url> health-assistant-live-avatar
cd health-assistant-live-avatar

cp docker/.env.example docker/.env
# Edit docker/.env with production keys (LiveKit Cloud, API keys, etc.)

docker volume create health-assistant-app-data
docker volume create health-assistant-recordings
```

Ensure the deploy user can run Docker without sudo:

```bash
sudo usermod -aG docker "$USER"
# log out and back in
```

## SSH key for GitHub Actions

On your **local machine**:

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy -N ""
```

On the **server**, add the public key:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Test from local:

```bash
ssh -i ~/.ssh/github_actions_deploy USER@YOUR_SERVER_IP
```

## GitHub repository secrets

Go to **Settings → Environments → production → Environment secrets** (or repository secrets):

| Secret            | Required | Example                                                    |
| ----------------- | -------- | ---------------------------------------------------------- |
| `SSH_HOST`        | Yes      | `203.0.113.10` or `myserver.example.com`                   |
| `SSH_USER`        | Yes      | `ubuntu` or your deploy user                               |
| `SSH_PRIVATE_KEY` | Yes      | Full private key (`-----BEGIN OPENSSH PRIVATE KEY-----` …) |
| `SSH_PORT`        | No       | `22`                                                       |
| `DEPLOY_PATH`     | No       | `/var/www/mykare-assessment/health-assistant-live-avatar`  |
| `LIVEKIT_MODE`    | No       | `cloud` (default), `local`, or `off`                       |

Optional: create a **production** environment under **Settings → Environments** and require approval before deploy.

## Blue-green ports

| Color | Frontend | Backend |
| ----- | -------- | ------- |
| blue  | 3000     | 8000    |
| green | 3002     | 8002    |

Active color is stored in `docker/.deploy-color`. Deploy updates nginx upstream automatically via `nginx/scripts/update-upstream.sh`.

## Nginx + SSL

See **[nginx/README.md](../nginx/README.md)**.

```bash
LIVEKIT=cloud bash docker/scripts/deploy.sh
sudo bash nginx/scripts/install.sh
curl -I http://mykare.backend.geeekgod.in/health/ready
sudo CERTBOT_EMAIL=you@example.com bash nginx/scripts/enable-ssl.sh
LIVEKIT=cloud bash docker/scripts/deploy.sh   # rebuild frontend with HTTPS API URL
```

`enable-ssl.sh` patches `docker/.env` with `https://mykare.backend.geeekgod.in` automatically.

## Manual deploy on server

```bash
cd /var/www/mykare-assessment/health-assistant-live-avatar
git pull origin main
LIVEKIT=cloud bash docker/scripts/deploy.sh
```

## Health checks & autoheal

| Service  | Health endpoint / check                                        |
| -------- | -------------------------------------------------------------- |
| backend  | `GET /health` (liveness), `GET /health/ready` (DB + readiness) |
| frontend | `GET /api/health`                                              |
| agent    | process check (`livekit_worker.worker`)                        |
| livekit  | HTTP probe on `:7880` (self-hosted profile only)               |

All app containers are labelled `autoheal=true`. Deploy and `make docker-up DETACH=1` start a singleton [willfarrell/autoheal](https://hub.docker.com/r/willfarrell/autoheal) container that watches Docker health status and restarts unhealthy containers.

```bash
bash docker/scripts/autoheal.sh   # start manually if needed
docker ps --filter name=health-assistant-autoheal
```

## Troubleshooting

- **`git pull` permission denied** — ensure deploy user owns the repo directory.
- **Docker permission denied** — add user to `docker` group.
- **`docker/.env` missing** — create from `docker/.env.example` on the server (never commit secrets).
- **Health check timeout** — check `docker compose -p health-assistant-green ps` and logs.
