import { useEffect, useRef, useState } from "react"
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
} from "recharts"
import { usd } from "./ui"

/* Hero: the before -> after savings story.
   Contract: accepts { before, after } and renders before.toFixed(2) and
   after.toFixed(2) as visible text (value labels on the bars + the figure rail).
   Do NOT remove those literal numeric strings — a test asserts /1278/ & /856.5/. */

function useCountUp(target: number, ms = 1100) {
  const [val, setVal] = useState(0)
  const raf = useRef<number | undefined>(undefined)
  useEffect(() => {
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (reduce || typeof requestAnimationFrame !== "function") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-shot snap to final value when motion is reduced / no rAF (jsdom)
      setVal(target)
      return
    }
    const start = performance.now()
    const from = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 3)
      setVal(from + (target - from) * eased)
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current)
    }
  }, [target, ms])
  return val
}

export function BillChart({ before, after }: { before: number; after: number }) {
  const saved = Math.max(0, before - after)
  const pct = before > 0 ? (saved / before) * 100 : 0
  const animatedSaved = useCountUp(saved)

  const data = [
    { name: "BEFORE", value: before, tone: "var(--color-block)" },
    { name: "AFTER", value: after, tone: "var(--color-allow)" },
  ]

  return (
    <section className="rise grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[var(--color-edge)] bg-[var(--color-edge)] shadow-[0_24px_70px_-34px_rgba(0,0,0,0.95)] lg:grid-cols-[1.05fr_1fr]">
      {/* LEFT — the saved figure, the emotional payload */}
      <div className="relative bg-[var(--color-panel)] p-6 sm:p-8">
        <div className="absolute inset-0 bg-[radial-gradient(420px_220px_at_30%_0%,var(--color-allow-glow),transparent_70%)]" />
        <div className="relative">
          <div className="mb-1 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.3em] text-[var(--color-ink-faint)]">
            Realised savings · per month
          </div>
          <div className="flex items-end gap-1">
            <span className="mb-2 text-2xl font-semibold text-[var(--color-ink-dim)]">
              $
            </span>
            <span className="tnum shimmer font-[family-name:var(--font-mono)] text-[clamp(3rem,7vw,5.25rem)] font-bold leading-none tracking-tight">
              {usd(animatedSaved)}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-allow)]/30 bg-[var(--color-allow)]/10 px-2.5 py-1 font-[family-name:var(--font-mono)] text-xs font-semibold text-[var(--color-allow)]">
              ↓ {pct.toFixed(1)}% of bill
            </span>
            <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--color-ink-faint)]">
              ${usd(saved * 12)} / yr if applied
            </span>
          </div>

          {/* figure rail — these carry the raw toFixed(2) strings the test asserts */}
          <div className="mt-7 grid grid-cols-2 gap-3 border-t border-[var(--color-edge)] pt-5">
            <Figure
              label="Bill before"
              value={before.toFixed(2)}
              accent="var(--color-block)"
            />
            <Figure
              label="Bill after"
              value={after.toFixed(2)}
              accent="var(--color-allow)"
            />
          </div>
        </div>
      </div>

      {/* RIGHT — the comparison bars */}
      <div className="bg-[var(--color-panel-2)] p-6 sm:p-7">
        <div className="mb-3 flex items-center justify-between">
          <div className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.3em] text-[var(--color-ink-faint)]">
            Monthly bill · before vs after
          </div>
          <div className="flex items-center gap-3 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-wider">
            <Legend color="var(--color-block)" label="before" />
            <Legend color="var(--color-allow)" label="after" />
          </div>
        </div>
        <div className="h-[176px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 26, right: 8, left: 8, bottom: 4 }}
              barCategoryGap="34%"
            >
              <XAxis
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{
                  fill: "var(--color-ink-faint)",
                  fontSize: 10,
                  fontFamily: "var(--font-mono)",
                  letterSpacing: 1.5,
                }}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive>
                {data.map((d) => (
                  <Cell key={d.name} fill={d.tone} fillOpacity={0.92} />
                ))}
                <LabelList
                  dataKey="value"
                  position="top"
                  formatter={(v: unknown) => `$${Number(v).toFixed(2)}`}
                  fill="var(--color-ink)"
                  fontSize={12}
                  fontFamily="var(--font-mono)"
                  fontWeight={600}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  )
}

function Figure({
  label,
  value,
  accent,
}: {
  label: string
  value: string
  accent: string
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: accent }} />
        <span className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em] text-[var(--color-ink-faint)]">
          {label}
        </span>
      </div>
      <div className="tnum font-[family-name:var(--font-mono)] text-2xl font-semibold text-[var(--color-ink)]">
        <span className="text-[var(--color-ink-faint)]">$</span>
        {value}
      </div>
    </div>
  )
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[var(--color-ink-faint)]">
      <span className="h-2 w-2 rounded-[2px]" style={{ background: color }} />
      {label}
    </span>
  )
}
