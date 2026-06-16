import type { AgentResponse, PlanResponse, ScanResponse } from "./types"

// Single source of truth for the backend base URL.
//   ""        => static $0 mode: render the bundled sample-snapshot.json, no backend.
//   "@origin" => live API on the same origin the SPA is served from (the Function
//                Compute deploy serves both the SPA and /api/* — no build-time URL).
//   <url>     => live API at an explicit base (local dev against a separate backend).
const RAW_BASE = import.meta.env.VITE_API_BASE ?? ""
export const BASE =
  RAW_BASE === "@origin"
    ? typeof window !== "undefined"
      ? window.location.origin
      : ""
    : RAW_BASE

async function getJSON<T>(path: string): Promise<T> {
  if (!BASE) {
    // static fallback: the bundled sample snapshot (no backend configured)
    const r = await fetch("/sample-snapshot.json")
    const all = await r.json()
    if (path.startsWith("/api/scan")) return all.scan as T
    if (path.startsWith("/api/plan")) return all.plan as T
    throw new Error("no backend configured")
  }
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error((await r.json()).error ?? r.statusText)
  return r.json() as Promise<T>
}

export const fetchScan = (provider = "mock") =>
  getJSON<ScanResponse>(`/api/scan?provider=${provider}`)

export const fetchPlan = (provider = "mock", maxBlast = 4, allowIrr = true) =>
  getJSON<PlanResponse>(
    `/api/plan?provider=${provider}&max_blast=${maxBlast}&allow_irreversible=${allowIrr}`,
  )

export async function runAgent(
  provider = "mock", auto = false, maxBlast = 4, allowIrr = true,
): Promise<AgentResponse> {
  if (!BASE) {
    const r = await fetch("/sample-snapshot.json")
    return (await r.json()).agent as AgentResponse
  }
  const r = await fetch(`${BASE}/api/agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, auto, max_blast: maxBlast, allow_irreversible: allowIrr }),
  })
  if (!r.ok) throw new Error((await r.json()).error ?? r.statusText)
  return r.json()
}

// SSE live agent stream; calls onEvent(name, data) per message. Terminal on
// "done" or "error" (a worker exception), and on a transport-level failure
// (synthesized as an "error" event) — always closes the EventSource so it
// never silently auto-reconnects or hangs the UI. maxBlast/allowIrr default to
// the same policy the static plan uses (4 / true) so the live and static demos
// show the same savings numbers.
export function streamAgent(
  provider: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- SSE payload is dynamic; the typed contract is enforced where consumers read specific fields
  onEvent: (name: string, data: any) => void,
  maxBlast = 4,
  allowIrr = true,
): EventSource {
  const es = new EventSource(
    `${BASE}/api/agent/stream?provider=${provider}&max_blast=${maxBlast}&allow_irreversible=${allowIrr}`,
  )
  let closed = false
  const finish = () => {
    closed = true
    es.close()
  }
  for (const name of ["tool_call", "proposal", "narrative", "tool_result", "done", "error"]) {
    es.addEventListener(name, (e) => {
      onEvent(name, JSON.parse((e as MessageEvent).data))
      if (name === "done" || name === "error") finish()
    })
  }
  es.onerror = () => {
    if (closed) return
    onEvent("error", { error: "stream connection failed" })
    finish()
  }
  return es
}
