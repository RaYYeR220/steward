# Steward

**Autonomous FinOps agent for Alibaba Cloud.** Steward discovers your cloud
resources, finds the money leaks, plans cost-cutting actions with explicit
blast-radius scores, executes them under a policy gate — and rolls back
automatically when a post-execution health check fails.

Built for the Qwen Cloud Global AI Hackathon (Autopilot Agent track).

**▶ Live demo:** [dashboard](https://rayyer220.github.io/steward/) (GitHub Pages SPA) →
[backend API](https://stewardashboard-ysmogrzgbv.eu-central-1.fcapp.run/api/health)
(live on **Alibaba Function Compute**, read-only / dry-run).

## How it works

```
discover ──> detect ──> plan ──> gate ──> execute ──> verify ──> report
 (cloud      (waste     (blast    (policy   (before-    (health     (markdown
  inventory)  findings)  scores,   rules,    state       checks,     run report)
                         safe-     budget    capture)    auto-
                         first     caps)                 rollback)
                         order)
```

- **Detectors** find five classes of waste: over-provisioned ECS instances,
  idle elastic IPs, unattached disks, orphaned old snapshots, and cold OSS
  buckets paying Standard-tier prices.
- **The planner** scores every proposed action 1-5 for blast radius and orders
  the plan safest-first.
- **The policy gate** is deterministic code outside LLM control: protected
  tags (`env=production` is untouchable by default), a blast-radius cap, an
  irreversibility opt-in, a monthly-change budget, and a per-run action cap.
- **The executor** captures before-state for every action, verifies health
  after execution, and rolls back automatically on failure. Disk deletions
  take a safety snapshot first, making them reversible. A failure halts the
  batch — it never cascades.

## Try it (no cloud account needed)

Phase 1 runs against an in-memory mock cloud seeded with a deliberately
wasteful account:

```bash
uv sync
uv run steward scan                  # inventory + waste findings
uv run steward plan                  # gated action plan with blast scores
uv run steward run                   # DRY RUN (default — nothing changes)
uv run steward run --execute --max-blast 4 --allow-irreversible
uv run steward run --execute --max-blast 4 --allow-irreversible --simulate-unhealthy i-staging-app   # watch the automatic rollback
```

Run the tests:

```bash
uv run pytest
```

## Agent mode (Qwen)

`steward agent` hands the investigation to Qwen (`qwen3.7-max` on Qwen Cloud,
OpenAI-compatible API): the model explores the account through tools
(`list_resources`, `get_metrics`, `get_findings`), proposes extra savings via
`propose_action`, and explains its reasoning. Everything it proposes still goes
through the same deterministic planner, policy gate, and safe executor.

```bash
# needs QWEN_API_KEY in .env (see .env.example)
uv run steward agent                 # investigate -> plan -> human y/N -> execute
uv run steward agent --auto          # full autopilot: no prompt, gates still apply
```

Safety rules specific to agent mode:

- **LLM proposals carry +1 blast radius** — they lack deterministic evidence.
- **`--auto` never executes LLM proposals.** They are gated out with
  "requires interactive approval"; only the rule-based findings auto-execute.
  Autonomy without blind trust in the model.
- **Every run is auditable.** The full tool-call transcript is saved to
  `reports/agent-transcript-*.json`; the agent's narrative lands in the report.
- **No key, no problem.** Without `QWEN_API_KEY` the agent degrades to a
  detector-only run with a warning.

## Live mode (real Alibaba Cloud)

With `ALIBABA_ACCESS_KEY_ID` / `ALIBABA_ACCESS_KEY_SECRET` / `ALIBABA_REGION` in
`.env`, Steward runs against the real account:

```bash
# --provider is a global flag: it comes before the subcommand
uv run steward --provider alibaba scan     # real inventory, CPU, and cost
uv run steward --provider alibaba agent    # Qwen investigates the real account
```

- **Reads are free** (ECS/CloudMonitor/OSS/BSS describe calls cost nothing).
- **Cost provenance is honest:** each resource is tagged billed / estimated /
  static; the report footnotes anything not from real billing data.
- **Live execution is safe by construction:** only cheap, reversible mutations
  run live (release an idle EIP, change an OSS bucket's storage class).
  Destructive actions (ECS resize with downtime, disk/snapshot deletion) are
  disabled on the live provider unless `STEWARD_LIVE_DESTRUCTIVE=1` is set —
  demo them on `--provider mock`.

Populate a $0 free-tier sandbox with `uv run python scripts/seed_sandbox.py`
and remove it with `scripts/teardown_sandbox.py`.

## Safety model

- **Dry-run by default.** `--execute` is an explicit opt-in.
- **Production is untouchable.** Resources tagged `env=production` are blocked
  by the gate no matter what the planner wants.
- **Irreversible actions are opt-in.** Releasing an EIP or deleting a snapshot
  cannot be undone, so they require `--allow-irreversible`.
- **Conservative blast-radius defaults.** Resizing a *running* instance scores
  4/5 (base 3 for a restart-requiring action, +1 because it interrupts a live
  resource), above the default cap of 3 — so applying ECS downsizes requires
  an explicit `--max-blast 4`. The agent never silently restarts live compute.
- **A failed rollback is loud.** If a rollback itself fails, the action is
  recorded as `ROLLBACK FAILED — MANUAL INTERVENTION REQUIRED` with the full
  before-state preserved in the run report, and the batch halts.
- **Sandbox only.** Steward is designed to run against a dedicated sandbox
  account. Never point it at a production account you are not prepared to
  modify.

## Roadmap

- [x] Phase 1 — core engine (detect / plan / gate / execute / rollback) on a mock cloud
- [x] Phase 2 — Qwen agent loop: Qwen3.7-Max plans and explains via function calling
- [x] Phase 3 — real Alibaba Cloud adapter (ECS, EIP, EBS, OSS + billing APIs)
- [x] Phase 4 — web dashboard
- [ ] Phase 5 — deployment on Alibaba Cloud Function Compute

## Dashboard (web)

A FastAPI backend exposes the engine as JSON + an SSE stream of the Qwen agent's
live tool calls; a static React SPA renders the FinOps story (bill, resources,
gated plan, before/after savings, agent narrative).

```bash
# backend (read-only / dry-run; real mutations stay in the CLI)
uv sync --extra api
uv run uvicorn steward.api.app:app --port 8000

# frontend (in another shell)
cd dashboard
echo "VITE_API_BASE=http://127.0.0.1:8000" > .env.local
npm install && npm run dev
```

The dashboard is **safe by construction**: the API is dry-run only, providers
are gated by `STEWARD_API_PROVIDERS`, and a missing key degrades gracefully.
With no backend configured the SPA renders a bundled sample snapshot, so it
deploys to OSS static hosting at $0.

## License

MIT
