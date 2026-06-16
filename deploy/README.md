# Phase 5 — deploy to Alibaba Cloud

## Live

- **Backend (Alibaba Function Compute):** https://stewardashboard-ysmogrzgbv.eu-central-1.fcapp.run
  — FC 3.0 custom-runtime web function serving the engine + `/api/*` (read-only / dry-run,
  `STEWARD_API_PROVIDERS=mock`). Config: `deploy/fc/`.
- **Browsable dashboard (GitHub Pages):** https://rayyer220.github.io/steward/
  — the SPA, built with `VITE_API_BASE=<the FC URL>`, rendered inline and calling the
  live FC API (the function has CORS `*`). This is the clickable demo.

The FC system domain `*.fcapp.run` force-downloads HTML (Alibaba anti-phishing), so the
SPA is hosted on GitHub Pages for in-browser rendering while the **backend runs on
Alibaba**. To serve everything from one Alibaba URL instead, bind a custom domain (CNAME)
to the function in the FC console.

### Redeploy the GitHub Pages frontend
```powershell
# IMPORTANT: build in PowerShell, NOT Git Bash — Git Bash mangles --base=/steward/
# into a Windows path. .env.production.local pins VITE_API_BASE to the FC URL.
cd dashboard; npm run build -- --base=/steward/
# then push dashboard/dist to the gh-pages branch (root), with an empty .nojekyll file.
```

---

Steward also deploys as a **single Function Compute (FC 3.0) container** that serves the
React dashboard *and* the `/api/*` endpoints from one HTTPS URL (`deploy/s.yaml` +
repo-root `Dockerfile`; needs a container registry). The function is **read-only / dry-run**
(`STEWARD_API_PROVIDERS=mock`) — a public deployment can never touch a real cloud account;
the real, reversible mutations stay in the CLI.

## Why Function Compute (not OSS static)

OSS static hosting was tried first and rejected: on the default `*.aliyuncs.com`
OSS domain, Alibaba forces `Content-Disposition: attachment` on HTML (anti-phishing),
so the SPA **downloads instead of rendering**, and there is no public `oss-website-*`
endpoint for these regions (confirmed `NXDOMAIN`). A browsable OSS site would need a
custom domain (CNAME) or CDN, which we don't have. FC URLs render HTML inline, so FC
serves both the SPA and the API from one origin. (`scripts/deploy_oss_site.py` remains
for an OSS+CDN setup later.)

## What's ready (proven locally)

- **`../Dockerfile`** — multi-stage build (Node builds the SPA → Python serves
  `steward.api.app:app` + the SPA on port 9000). Verified locally:
  `GET /` → 200 `text/html` (no forced download), `GET /api/health` → ok,
  `GET /api/scan?provider=mock` → `total_monthly_usd: 1278.0`.
- **`s.yaml`** — the FC 3.0 deploy config (custom-container web function, anonymous
  HTTP trigger, small free-tier resources).
- The SPA is built with `VITE_API_BASE=@origin` (`dashboard/.env.production`), so it
  calls the API on its own origin — no deploy-time URL needed.

### Run it locally right now ($0, no cloud)
```bash
docker build -t steward:local ..      # from this deploy/ dir, or `docker build -t steward:local .` from repo root
docker run --rm -p 9000:9000 steward:local
# open http://localhost:9000
```

## Blocker (account-side — needs the account owner in the console)

The AccessKey in `.env` belongs to the RAM user **`steward-agent`**, which has only the
FinOps *read* permissions (ECS/VPC/OSS/CMS). It lacks deploy permissions, so:
- Container Registry: `GetAuthorizationToken` → `AUTHENTICATION_FAILED: user jurisdiction error`.
- Function Compute: no create/update rights.

**To unblock (Alibaba console, as the account owner):**
1. Activate **Function Compute** and **Container Registry** (both have a free tier).
   For ACR, create an **Enterprise** instance (free tier) + a namespace (e.g. `steward`),
   *or* enable the Personal/default registry.
2. Grant the `steward-agent` RAM user: **`AliyunFCFullAccess`** and
   **`AliyunContainerRegistryFullAccess`** (RAM → Users → steward-agent → Add Permissions).
   *Or* run the deploy with the **root account** AccessKey instead (full rights).

## Deploy (once unblocked)

### Path A — container (the proven artifact)
```bash
# 1. log in to ACR with a temporary token (no console password needed):
#    s can do this, or use `aliyun cr GetAuthorizationToken` + `docker login`.
# 2. build + push the image:
docker build -t steward:local ..
docker tag steward:local registry.eu-central-1.cr.aliyuncs.com/<namespace>/steward:latest
docker push registry.eu-central-1.cr.aliyuncs.com/<namespace>/steward:latest
# 3. deploy the function:
export STEWARD_IMAGE=registry.eu-central-1.cr.aliyuncs.com/<namespace>/steward:latest
export QWEN_API_KEY=...        # optional — enables the live agent on the deployed site
s deploy -y                    # prints the public function URL
```

### Path B — zip, custom runtime (no ACR)
If you'd rather skip Container Registry: switch `s.yaml` to `runtime: custom.debian10`
with a `bootstrap` that runs `python3 -m uvicorn steward.api.app:app --host 0.0.0.0 --port 9000`,
include `src/steward` + `dashboard/dist`, and use `s build --use-docker` to vendor
Linux-compatible deps (`fastapi uvicorn openai`), then `s deploy -y`. Needs only FC
activated + `AliyunFCFullAccess` (no ACR).

## Verify after deploy
```bash
curl <url>/api/health                       # {"status":"ok"}
curl -i <url>/ | grep -i content-disposition # must be ABSENT (renders inline)
curl "<url>/api/scan?provider=mock"          # total_monthly_usd: 1278.0
```
