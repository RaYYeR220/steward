import type { Decision } from "../types"
import { BlastMeter, Panel, Tag, usd } from "./ui"

/* The gated remediation plan: "LLM proposes, policy disposes."
   Contract: accepts { decisions } and renders, as visible text, each
   decision.resource_id, the literal strings ALLOW / BLOCK (here inside badges),
   and the block-reason text via reasons.join. Tests assert these. */

const ACTION_LABEL: Record<string, string> = {
  release_eip: "Release EIP",
  delete_disk: "Delete disk",
  delete_snapshot: "Delete snapshot",
  change_oss_class: "Re-tier OSS",
  resize_ecs: "Resize ECS",
}

function GateBadge({ allowed }: { allowed: boolean }) {
  if (allowed) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-allow)]/40 bg-[var(--color-allow)]/12 px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] font-bold tracking-[0.12em] text-[var(--color-allow)] shadow-[0_0_18px_-6px_var(--color-allow-glow)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-allow)]" />
        ALLOW
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-block)]/40 bg-[var(--color-block)]/12 px-2.5 py-1 font-[family-name:var(--font-mono)] text-[11px] font-bold tracking-[0.12em] text-[var(--color-block)] shadow-[0_0_18px_-6px_var(--color-block-glow)]">
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-block)]" />
      BLOCK
    </span>
  )
}

export function PlanTable({ decisions }: { decisions: Decision[] }) {
  const allowed = decisions.filter((d) => d.allowed).length
  const blocked = decisions.length - allowed

  return (
    <Panel
      eyebrow="Policy gate"
      title="Remediation plan"
      right={
        <div className="flex items-center gap-2">
          <Tag tone="allow">{allowed} permitted</Tag>
          <Tag tone="block">{blocked} gated</Tag>
        </div>
      }
    >
      {/* column legend */}
      <div className="mb-2 hidden grid-cols-[1.5fr_1fr_auto_auto_auto] items-center gap-4 px-3 font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em] text-[var(--color-ink-faint)] lg:grid">
        <span>Resource · action</span>
        <span>Blast radius</span>
        <span className="text-right">$ / mo</span>
        <span className="text-right">Gate</span>
        <span className="w-2" />
      </div>

      <ul className="flex flex-col gap-2">
        {decisions.map((d) => {
          const action = ACTION_LABEL[d.action_type] ?? d.action_type
          return (
            <li
              key={d.resource_id + d.action_type}
              className={`group grid grid-cols-1 items-center gap-3 rounded-xl border px-3.5 py-3 transition-colors lg:grid-cols-[1.5fr_1fr_auto_auto] lg:gap-4 ${
                d.allowed
                  ? "border-[var(--color-edge)] bg-[var(--color-panel-2)]/60 hover:border-[var(--color-allow)]/30"
                  : "border-[var(--color-block)]/25 bg-[var(--color-block)]/[0.04] hover:border-[var(--color-block)]/45"
              }`}
            >
              {/* resource + action */}
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{
                      background: d.allowed
                        ? "var(--color-allow)"
                        : "var(--color-block)",
                    }}
                  />
                  <span className="tnum truncate font-[family-name:var(--font-mono)] text-sm font-semibold text-[var(--color-ink)]">
                    {d.resource_id}
                  </span>
                </div>
                <div className="mt-1 pl-4 text-xs text-[var(--color-ink-dim)]">
                  {action}
                  {d.source && (
                    <span className="ml-1.5 text-[var(--color-ink-faint)]">
                      · {d.source}
                    </span>
                  )}
                </div>
              </div>

              {/* blast */}
              <div className="pl-4 lg:pl-0">
                <BlastMeter value={d.blast_radius} />
              </div>

              {/* saving */}
              <div className="pl-4 text-left lg:pl-0 lg:text-right">
                <span className="tnum font-[family-name:var(--font-mono)] text-sm font-semibold text-[var(--color-ink)]">
                  <span className="text-[var(--color-ink-faint)]">$</span>
                  {usd(d.monthly_saving_usd)}
                </span>
              </div>

              {/* gate + reason */}
              <div className="flex min-w-0 flex-col items-start gap-1.5 pl-4 lg:items-end lg:pl-0">
                <GateBadge allowed={d.allowed} />
                {!d.allowed && d.reasons.length > 0 && (
                  <span className="max-w-full font-[family-name:var(--font-mono)] text-[11px] leading-snug text-[var(--color-block)]/85 lg:text-right">
                    {d.reasons.join("; ")}
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
