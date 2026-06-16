import type { Decision } from "../types"
import { Panel } from "./ui"

/* Dry-run execution log: what the executor WOULD do under the gate.
   Contract: { decisions } unchanged. */

export function RunLog({ decisions }: { decisions: Decision[] }) {
  return (
    <Panel eyebrow="Dry run" title="Execution log">
      <ul className="flex flex-col gap-1.5 font-[family-name:var(--font-mono)] text-[12.5px]">
        {decisions.map((d) => (
          <li
            key={d.resource_id + d.action_type}
            className="flex items-center gap-2.5 rounded-lg border border-[var(--color-edge)] bg-[var(--color-panel-2)]/50 px-3 py-2"
          >
            <span
              className="shrink-0 text-[var(--color-ink-faint)]"
              aria-hidden
            >
              {d.allowed ? "›" : "✕"}
            </span>
            <span className="tnum text-[var(--color-ink)]">{d.resource_id}</span>
            <span className="text-[var(--color-ink-faint)]">—</span>
            {d.allowed ? (
              <span className="font-medium text-[var(--color-allow)]">
                would execute
              </span>
            ) : (
              <span className="font-medium text-[var(--color-block)]">
                blocked
              </span>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}
