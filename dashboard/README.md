# Steward Dashboard

The web dashboard for **Steward** — an autonomous FinOps agent for Alibaba Cloud.
A static React + TypeScript + Tailwind SPA that renders the FinOps story: current
bill, resources, the gated remediation plan (ALLOW/BLOCK with blast-radius and
reasons), before/after savings, and the Qwen agent's live tool-call feed and
narrative.

It talks to the read-only / dry-run FastAPI backend (`steward.api.app`) over JSON
+ an SSE stream. With no backend configured (`VITE_API_BASE` unset) it renders the
bundled `public/sample-snapshot.json`, so it deploys to OSS static hosting at $0.

See the **`## Dashboard (web)`** section of the [repo-root README](../README.md)
for the full run/build instructions.

## Quick start

```bash
npm install
npm run dev        # static $0 mode (bundled sample snapshot)
npm run build      # type-check + production bundle
npm test           # Vitest component tests
```

To point it at a live backend, create `.env.local` with
`VITE_API_BASE=http://127.0.0.1:8000` (see the root README).

## Stack

Vite · React + TypeScript · Tailwind v4 · Recharts · Vitest + Testing Library.
