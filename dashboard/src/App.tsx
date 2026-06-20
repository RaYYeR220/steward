import { useEffect, useState } from "react"
import { fetchScan, fetchPlan, runAgent, streamAgent, BASE } from "./api"
import type { ScanResponse, PlanResponse } from "./types"
import { BillChart } from "./components/BillChart"
import { ResourceTable } from "./components/ResourceTable"
import { PlanTable } from "./components/PlanTable"
import { RunLog } from "./components/RunLog"
import { AgentPanel, type AgentLine } from "./components/AgentPanel"
import { usd } from "./components/ui"

export default function App() {
  const [provider, setProvider] = useState("mock")
  const [scan, setScan] = useState<ScanResponse | null>(null)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [lines, setLines] = useState<AgentLine[]>([])
  const [narrative, setNarrative] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    fetchScan(provider).then(setScan).catch(() => setScan(null))
    fetchPlan(provider).then(setPlan).catch(() => setPlan(null))
  }, [provider])

  function onRunAgent() {
    setLines([]); setNarrative(null); setRunning(true)
    const usePoll = import.meta.env.VITE_AGENT_MODE === "poll"
    if (!BASE || usePoll) {
      runAgent(provider)
        .then((a) => {
          setNarrative(a.narrative)
          setPlan({ decisions: a.decisions, allowed_saving_usd: a.allowed_saving_usd, blocked_saving_usd: a.blocked_saving_usd })
          // surface the transcript as feed lines (no live stream in poll mode)
          setLines((a.transcript ?? []).map((e: any) => ({
            name: e.tool_calls ? "tool_call" : e.role === "tool" ? "tool_result" : "narrative",
            text: JSON.stringify(e).slice(0, 200),
          })))
          setRunning(false)
        })
        .catch((err) => { setNarrative(`agent error: ${err?.message ?? err}`); setRunning(false) })
      return
    }
    streamAgent(provider, (name, data) => {
      if (name === "done") { setNarrative(data.narrative); setPlan({ decisions: data.decisions, allowed_saving_usd: data.allowed_saving_usd, blocked_saving_usd: data.blocked_saving_usd }); setRunning(false) }
      else if (name === "error") { setNarrative(`agent stream error: ${data.error ?? "unknown"}`); setRunning(false) }
      else setLines((prev) => [...prev, { name, text: JSON.stringify(data).slice(0, 200) }])
    })
  }

  const before = scan?.total_monthly_usd ?? 0
  const after = before - (plan?.allowed_saving_usd ?? 0)
  const allowedSaving = plan?.allowed_saving_usd ?? 0
  const blockedSaving = plan?.blocked_saving_usd ?? 0

  return (
    <div className="min-h-screen">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-7 sm:px-8 sm:py-10">
        {/* ── header ─────────────────────────────────────────────── */}
        <header className="rise mb-8 flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3.5">
            <Mark />
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-[26px] font-bold leading-none tracking-tight text-[var(--color-ink)]">
                  Steward
                </h1>
                <span className="rounded-md border border-[var(--color-brand)]/30 bg-[var(--color-brand)]/10 px-1.5 py-0.5 font-[family-name:var(--font-mono)] text-[9px] font-semibold uppercase tracking-[0.18em] text-[var(--color-brand)]">
                  FinOps · autopilot
                </span>
              </div>
              <p className="mt-1.5 max-w-xl text-sm text-[var(--color-ink-dim)]">
                Autonomous FinOps for Alibaba Cloud —{" "}
                <span className="text-[var(--color-ink)]">
                  the LLM proposes, policy disposes.
                </span>
              </p>
            </div>
          </div>

          {/* controls */}
          <div className="flex items-center gap-2.5">
            <div className="flex items-center rounded-xl border border-[var(--color-edge)] bg-[var(--color-panel)] p-1">
              {["mock", "alibaba"].map((p) => (
                <button
                  key={p}
                  onClick={() => setProvider(p)}
                  className={`rounded-lg px-3 py-1.5 font-[family-name:var(--font-mono)] text-xs font-medium uppercase tracking-wider transition-colors ${
                    provider === p
                      ? "bg-[var(--color-edge-2)] text-[var(--color-ink)]"
                      : "text-[var(--color-ink-faint)] hover:text-[var(--color-ink-dim)]"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
            <button
              onClick={onRunAgent}
              disabled={running}
              className="group relative inline-flex items-center gap-2 overflow-hidden rounded-xl border border-[var(--color-allow)]/40 bg-[var(--color-allow)]/12 px-4 py-2 font-[family-name:var(--font-mono)] text-xs font-bold uppercase tracking-[0.14em] text-[var(--color-allow)] transition-all hover:bg-[var(--color-allow)]/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full bg-[var(--color-allow)] ${
                  running ? "live-dot" : ""
                }`}
              />
              {running ? "running…" : "Run agent"}
            </button>
          </div>
        </header>

        {/* ── stat strip ─────────────────────────────────────────── */}
        <div className="rise mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Monthly bill" value={`$${usd(before)}`} />
          <Stat label="Resources" value={`${scan?.resources.length ?? 0}`} />
          <Stat
            label="Allowed savings"
            value={`$${usd(allowedSaving)}`}
            accent="var(--color-allow)"
          />
          <Stat
            label="Blocked by gate"
            value={`$${usd(blockedSaving)}`}
            accent="var(--color-block)"
          />
        </div>

        {/* ── hero ───────────────────────────────────────────────── */}
        <div className="mb-6">
          <BillChart before={before} after={after} />
        </div>

        {/* ── plan + agent ───────────────────────────────────────── */}
        <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.35fr_1fr]">
          <div className="flex flex-col gap-6">
            {plan && <PlanTable decisions={plan.decisions} />}
            {plan && <RunLog decisions={plan.decisions} />}
          </div>
          <AgentPanel lines={lines} narrative={narrative} />
        </div>

        {/* ── inventory ──────────────────────────────────────────── */}
        {scan && <ResourceTable resources={scan.resources} />}

        {/* ── footer ─────────────────────────────────────────────── */}
        <footer className="mt-10 flex flex-col items-start justify-between gap-2 border-t border-[var(--color-edge)] pt-5 text-xs text-[var(--color-ink-faint)] sm:flex-row sm:items-center">
          <span className="font-[family-name:var(--font-mono)]">
            steward · dry-run · safe by construction
          </span>
          <span className="font-[family-name:var(--font-mono)]">
            {BASE ? "live API" : "bundled sample snapshot · $0 hosting"}
          </span>
        </footer>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string
  value: string
  accent?: string
}) {
  return (
    <div className="rounded-xl border border-[var(--color-edge)] bg-[var(--color-panel)]/70 px-4 py-3">
      <div className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em] text-[var(--color-ink-faint)]">
        {label}
      </div>
      <div
        className="tnum mt-1 font-[family-name:var(--font-mono)] text-xl font-semibold"
        style={{ color: accent ?? "var(--color-ink)" }}
      >
        {value}
      </div>
    </div>
  )
}

/* brand glyph — a shield/ledger mark drawn in CSS, no asset dependency */
function Mark() {
  return (
    <div className="relative grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-[var(--color-edge-2)] bg-[var(--color-panel)] shadow-[0_0_30px_-10px_var(--color-allow-glow)]">
      <div className="absolute inset-0 rounded-xl bg-[radial-gradient(60%_60%_at_50%_30%,var(--color-allow-glow),transparent)]" />
      <svg
        viewBox="0 0 24 24"
        className="relative h-6 w-6"
        fill="none"
        stroke="var(--color-allow)"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 2.5 4 5.5v6c0 5 3.4 8.4 8 10 4.6-1.6 8-5 8-10v-6L12 2.5Z" />
        <path d="M8.5 12.2l2.4 2.4 4.6-4.8" stroke="var(--color-brand)" />
      </svg>
    </div>
  )
}
