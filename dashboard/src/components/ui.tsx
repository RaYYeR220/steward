import type { ReactNode } from "react"

/* Shared presentational primitives for the Steward control-room UI.
   Pure styling — no data-contract logic lives here. */

export function Panel({
  title,
  eyebrow,
  right,
  children,
  className = "",
  style,
}: {
  title?: string
  eyebrow?: string
  right?: ReactNode
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <section
      className={`rise rounded-2xl border border-[var(--color-edge)] bg-[var(--color-panel)]/80 backdrop-blur-sm shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset,0_24px_60px_-30px_rgba(0,0,0,0.9)] ${className}`}
      style={style}
    >
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-[var(--color-edge)] px-5 py-3.5">
          <div className="min-w-0">
            {eyebrow && (
              <div className="mb-0.5 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.28em] text-[var(--color-ink-faint)]">
                {eyebrow}
              </div>
            )}
            {title && (
              <h2 className="truncate text-[15px] font-semibold tracking-tight text-[var(--color-ink)]">
                {title}
              </h2>
            )}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

/* 1–5 blast-radius meter rendered as pips. Higher = hotter. */
export function BlastMeter({ value, max = 5 }: { value: number; max?: number }) {
  const v = Math.max(0, Math.min(max, value))
  const hot = v >= 4
  const color = hot
    ? "var(--color-block)"
    : v === 3
      ? "var(--color-warn)"
      : "var(--color-brand)"
  return (
    <div className="flex items-center gap-2" title={`blast radius ${v}/${max}`}>
      <div className="flex gap-[3px]">
        {Array.from({ length: max }).map((_, i) => (
          <span
            key={i}
            className="h-3.5 w-[6px] rounded-[2px] transition-colors"
            style={{
              background: i < v ? color : "var(--color-edge-2)",
              boxShadow: i < v ? `0 0 8px ${color}55` : "none",
            }}
          />
        ))}
      </div>
      <span className="tnum font-[family-name:var(--font-mono)] text-[11px] text-[var(--color-ink-dim)]">
        {v}/{max}
      </span>
    </div>
  )
}

/* small source/status chip */
export function Tag({
  children,
  tone = "neutral",
}: {
  children: ReactNode
  tone?: "neutral" | "allow" | "block" | "warn" | "brand"
}) {
  const tones: Record<string, string> = {
    neutral:
      "border-[var(--color-edge-2)] bg-[var(--color-panel-2)] text-[var(--color-ink-dim)]",
    allow:
      "border-[var(--color-allow)]/35 bg-[var(--color-allow)]/10 text-[var(--color-allow)]",
    block:
      "border-[var(--color-block)]/35 bg-[var(--color-block)]/10 text-[var(--color-block)]",
    warn: "border-[var(--color-warn)]/35 bg-[var(--color-warn)]/10 text-[var(--color-warn)]",
    brand:
      "border-[var(--color-brand)]/35 bg-[var(--color-brand)]/10 text-[var(--color-brand)]",
  }
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-[family-name:var(--font-mono)] text-[10px] font-medium uppercase tracking-[0.1em] ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

// eslint-disable-next-line react-refresh/only-export-components -- small shared formatter colocated with the ui primitives
export function usd(n: number): string {
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
