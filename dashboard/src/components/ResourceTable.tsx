import type { Resource } from "../types"
import { Panel, Tag, usd } from "./ui"

/* Account inventory. Contract: { resources } unchanged. */

const TYPE_LABEL: Record<string, string> = {
  ecs_instance: "ECS",
  disk: "Disk",
  eip: "EIP",
  snapshot: "Snapshot",
  oss_bucket: "OSS",
}

function statusTone(status: string): "allow" | "warn" | "neutral" {
  if (status === "running" || status === "in_use") return "allow"
  if (status === "available") return "warn" // unattached / idle
  return "neutral"
}

export function ResourceTable({ resources }: { resources: Resource[] }) {
  const total = resources.reduce((s, r) => s + r.monthly_cost_usd, 0)
  return (
    <Panel
      eyebrow="Inventory"
      title="Discovered resources"
      right={
        <span className="tnum font-[family-name:var(--font-mono)] text-xs text-[var(--color-ink-dim)]">
          {resources.length} resources · ${usd(total)}/mo
        </span>
      }
    >
      <div className="thin-scroll -mx-1 overflow-x-auto px-1">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--color-edge)] text-left font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.18em] text-[var(--color-ink-faint)]">
              <th className="py-2 pr-3 font-medium">Resource</th>
              <th className="py-2 pr-3 font-medium">Type</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 text-right font-medium">$ / mo</th>
              <th className="py-2 pr-1 text-right font-medium">Cost source</th>
            </tr>
          </thead>
          <tbody>
            {resources.map((r) => (
              <tr
                key={r.id}
                className="border-b border-[var(--color-edge)]/60 transition-colors last:border-0 hover:bg-[var(--color-panel-2)]/40"
              >
                <td className="py-2.5 pr-3">
                  <div className="tnum font-[family-name:var(--font-mono)] text-[13px] font-medium text-[var(--color-ink)]">
                    {r.id}
                  </div>
                  <div className="text-xs text-[var(--color-ink-faint)]">
                    {r.name}
                  </div>
                </td>
                <td className="py-2.5 pr-3">
                  <Tag tone="brand">{TYPE_LABEL[r.type] ?? r.type}</Tag>
                </td>
                <td className="py-2.5 pr-3">
                  <Tag tone={statusTone(r.status)}>{r.status}</Tag>
                </td>
                <td className="tnum py-2.5 pr-3 text-right font-[family-name:var(--font-mono)] text-[13px] text-[var(--color-ink)]">
                  <span className="text-[var(--color-ink-faint)]">$</span>
                  {usd(r.monthly_cost_usd)}
                </td>
                <td className="py-2.5 pr-1 text-right">
                  <Tag tone="neutral">{r.cost_source}</Tag>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
