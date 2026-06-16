import { useEffect, useRef } from "react"
import { Panel } from "./ui"

export interface AgentLine {
  name: string
  text: string
}

/* Live agent tool-call feed rendered as a control-room terminal stream,
   plus the model's closing narrative. Contract: { lines, narrative } unchanged. */

const EVENT_TONE: Record<string, string> = {
  tool_call: "var(--color-brand)",
  tool_result: "var(--color-allow)",
  proposal: "var(--color-warn)",
  narrative: "var(--color-brand-2)",
  error: "var(--color-block)",
}

export function AgentPanel({
  lines,
  narrative,
}: {
  lines: AgentLine[]
  narrative: string | null
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const live = lines.length > 0 && !narrative

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines.length, narrative])

  return (
    <Panel
      eyebrow="Qwen agent"
      title="Investigation stream"
      right={
        <span className="inline-flex items-center gap-2 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em]">
          <span
            className={`h-2 w-2 rounded-full ${live ? "live-dot" : ""}`}
            style={{
              background: live ? "var(--color-allow)" : "var(--color-ink-faint)",
            }}
          />
          <span className="text-[var(--color-ink-dim)]">
            {live ? "streaming" : narrative ? "idle" : "standby"}
          </span>
        </span>
      }
    >
      {/* terminal window */}
      <div className="overflow-hidden rounded-xl border border-[var(--color-edge)] bg-[#06080d]">
        <div className="flex items-center gap-1.5 border-b border-[var(--color-edge)] bg-[var(--color-panel-2)] px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-block)]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-warn)]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-allow)]/70" />
          <span className="ml-2 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em] text-[var(--color-ink-faint)]">
            steward · agent.trace
          </span>
        </div>
        <div
          ref={scrollRef}
          className="thin-scroll scanlines max-h-64 min-h-[120px] overflow-y-auto px-4 py-3 font-[family-name:var(--font-mono)] text-[12.5px] leading-relaxed"
        >
          {lines.length === 0 ? (
            <div className="text-[var(--color-ink-faint)]">
              <span className="text-[var(--color-allow)]">$</span> awaiting run —
              press{" "}
              <span className="text-[var(--color-brand)]">Run agent</span> to
              stream live tool calls
              <span className="live-dot ml-1 inline-block text-[var(--color-ink-dim)]">
                ▋
              </span>
            </div>
          ) : (
            lines.map((l, i) => {
              const tone = EVENT_TONE[l.name] ?? "var(--color-ink-dim)"
              return (
                <div key={i} className="flex gap-2 py-[1px]">
                  <span className="select-none text-[var(--color-ink-faint)]">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span
                    className="shrink-0 font-semibold uppercase tracking-wide"
                    style={{ color: tone }}
                  >
                    {l.name}
                  </span>
                  <span className="break-all text-[var(--color-ink-dim)]">
                    {l.text}
                  </span>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* narrative */}
      {narrative && (
        <div className="rise mt-4 rounded-xl border border-[var(--color-brand-2)]/25 bg-[var(--color-brand-2)]/[0.06] p-4">
          <div className="mb-1.5 flex items-center gap-2 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.24em] text-[var(--color-brand)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-brand)]" />
            Agent narrative
          </div>
          <p className="text-[13.5px] leading-relaxed text-[var(--color-ink)]/90">
            {narrative}
          </p>
        </div>
      )}
    </Panel>
  )
}
