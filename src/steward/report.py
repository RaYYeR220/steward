"""Render a run into the Markdown report that ships to the operator."""
from __future__ import annotations

from steward.models import ExecutionStatus, RunResult


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


_STATUS_LABEL = {
    ExecutionStatus.DRY_RUN: "DRY RUN (no change made)",
    ExecutionStatus.EXECUTED: "EXECUTED",
    ExecutionStatus.FAILED: "FAILED",
    ExecutionStatus.ROLLED_BACK: "ROLLED BACK",
    ExecutionStatus.ROLLBACK_FAILED: "ROLLBACK FAILED — MANUAL INTERVENTION REQUIRED",
    ExecutionStatus.BLOCKED: "BLOCKED BY POLICY",
    ExecutionStatus.NOT_REACHED: "NOT REACHED",
}

_NEEDS_EXPLANATION = {
    ExecutionStatus.BLOCKED,
    ExecutionStatus.FAILED,
    ExecutionStatus.ROLLED_BACK,
    ExecutionStatus.ROLLBACK_FAILED,
    ExecutionStatus.NOT_REACHED,
}


def render_report(
    result: RunResult, dry_run: bool, narrative: str | None = None
) -> str:
    lines = ["# Steward run report", ""]
    mode = "Dry run — no changes were made." if dry_run else "Execute mode."
    lines.append(f"**Mode:** {mode}")
    lines.append(f"**Monthly savings applied:** ${result.executed_saving_usd:.2f}")
    lines.append("")
    lines.append("| Resource | Action | Est. saving / mo | Blast | Outcome |")
    lines.append("|---|---|---|---|---|")
    for record in result.records:
        planned = record.action
        res = planned.finding.resource
        lines.append(
            f"| {_cell(res.name)} (`{res.id}`) | {planned.action.type.value} "
            f"| ${planned.monthly_saving_usd:.2f} | {planned.blast_radius}/5 "
            f"| {_STATUS_LABEL[record.status]} |"
        )
    lines.append("")

    if narrative:
        lines.append("## Agent narrative")
        lines.append("")
        lines.append(narrative)
        lines.append("")

    explanations = [r for r in result.records if r.status in _NEEDS_EXPLANATION]
    if explanations:
        lines.append("## Skipped, blocked, and recovered actions")
        for record in explanations:
            res = record.action.finding.resource
            detail = "; ".join(record.reasons) if record.reasons else (record.error or "")
            lines.append(f"- **{res.id}** — {_STATUS_LABEL[record.status]}: {detail}")
        lines.append("")

    lines.append("## Why each action was proposed")
    for record in result.records:
        finding = record.action.finding
        lines.append(f"- **{finding.resource.id}** ({finding.kind}): {finding.evidence}")
        for reason in record.action.blast_reasons:
            lines.append(f"  - blast: {reason}")
    sources = {r.action.finding.resource.cost_source for r in result.records}
    if sources & {"estimated", "static"}:
        lines.append("")
        lines.append(
            "> Costs marked estimated or static are not from actual billing data."
        )
    return "\n".join(lines) + "\n"
