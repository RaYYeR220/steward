"""Command-line interface.

Commands:
    steward scan   list resources and waste findings
    steward plan   show the gated action plan
    steward run    run the plan (dry-run unless --execute)
    steward agent  LLM-driven investigation, then a gated run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from steward.config import load_qwen_settings
from steward.demo_seed import seed_demo
from steward.detectors import run_detectors
from steward.executor import run as execute_run
from steward.llm.agent import AgentResult, investigate
from steward.llm.client import LLMError, QwenClient
from steward.planner import build_plan
from steward.policy import Policy, gate
from steward.providers.base import CloudError
from steward.report import render_report


def _build_alibaba_provider():
    from steward.providers.alibaba.config import load_alibaba_config
    from steward.providers.alibaba.provider import AlibabaCloudProvider

    config = load_alibaba_config()
    allow_destructive = bool(os.environ.get("STEWARD_LIVE_DESTRUCTIVE"))
    return AlibabaCloudProvider(config, allow_destructive=allow_destructive)


def make_provider(name: str):
    if name == "mock":
        return seed_demo()
    if name == "alibaba":
        return _build_alibaba_provider()
    raise SystemExit(f"unknown provider: {name!r} (supported: mock, alibaba)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steward", description="Autonomous FinOps agent for Alibaba Cloud"
    )
    parser.add_argument("--provider", default="mock")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="list resources and waste findings")
    plan_parser = sub.add_parser("plan", help="show the gated action plan")
    plan_parser.add_argument("--max-blast", type=int, default=3)
    plan_parser.add_argument("--allow-irreversible", action="store_true")
    run_parser = sub.add_parser("run", help="run the plan (dry-run unless --execute)")
    run_parser.add_argument(
        "--execute", action="store_true", help="actually apply changes"
    )
    run_parser.add_argument("--max-blast", type=int, default=3)
    run_parser.add_argument("--allow-irreversible", action="store_true")
    run_parser.add_argument(
        "--report-out", type=Path, default=Path("reports/latest-run.md")
    )
    run_parser.add_argument(
        "--simulate-unhealthy",
        metavar="RESOURCE_ID",
        help="demo knob (mock provider): make this resource fail health checks",
    )
    agent_parser = sub.add_parser(
        "agent", help="LLM-driven investigation, then a gated run"
    )
    agent_parser.add_argument(
        "--auto",
        action="store_true",
        help="skip the human checkpoint; LLM proposals stay blocked by policy, detector findings execute normally",
    )
    agent_parser.add_argument("--max-blast", type=int, default=3)
    agent_parser.add_argument("--allow-irreversible", action="store_true")
    agent_parser.add_argument(
        "--report-out", type=Path, default=Path("reports/latest-run.md")
    )
    agent_parser.add_argument(
        "--simulate-unhealthy",
        metavar="RESOURCE_ID",
        help="demo knob (mock provider): make this resource fail health checks",
    )
    agent_parser.add_argument("--max-tool-calls", type=int, default=20)
    return parser


def _print_warnings(provider, console: Console) -> None:
    """Surface a live provider's partial-failure warnings (e.g. a disabled service)."""
    for warning in getattr(provider, "last_warnings", []):
        console.print(f"[yellow]warning: {warning}[/yellow]")


def _cmd_scan(provider, console: Console) -> int:
    resources = sorted(provider.list_resources(), key=lambda r: -r.monthly_cost_usd)
    _print_warnings(provider, console)
    table = Table(title=f"Resources ({len(resources)})")
    for column in ("ID", "Type", "Name", "Status", "Tags", "$/mo"):
        table.add_column(column)
    total = 0.0
    for res in resources:
        total += res.monthly_cost_usd
        tags = ",".join(f"{k}={v}" for k, v in res.tags.items())
        table.add_row(
            res.id, res.type.value, res.name, res.status, tags,
            f"{res.monthly_cost_usd:.2f}",
        )
    console.print(table)
    console.print(f"Total monthly bill: ${total:.2f}")

    findings = run_detectors(provider)
    ftable = Table(title=f"Waste findings ({len(findings)})")
    for column in ("Resource", "Kind", "Evidence", "Saving $/mo"):
        ftable.add_column(column)
    for finding in findings:
        ftable.add_row(
            finding.resource.id,
            finding.kind,
            finding.evidence,
            f"{finding.monthly_saving_usd:.2f}",
        )
    console.print(ftable)
    potential = sum(f.monthly_saving_usd for f in findings)
    console.print(f"Potential monthly saving: ${potential:.2f}")
    return 0


def _plan_table(decisions) -> Table:
    table = Table(title="Action plan (safe-first order)")
    for column in ("#", "Resource", "Action", "Saving $/mo", "Blast", "Gate"):
        table.add_column(column)
    for index, decision in enumerate(decisions, 1):
        planned = decision.action
        gate_label = (
            "ALLOW" if decision.allowed else "BLOCK: " + "; ".join(decision.reasons)
        )
        table.add_row(
            str(index),
            planned.finding.resource.id,
            planned.action.type.value,
            f"{planned.monthly_saving_usd:.2f}",
            f"{planned.blast_radius}/5",
            gate_label,
        )
    return table


def _cmd_plan(provider, console: Console, policy: Policy) -> int:
    findings = run_detectors(provider)
    plan = build_plan(findings, provider)
    decisions = gate(plan, policy)
    console.print(_plan_table(decisions))
    allowed_usd = sum(d.action.monthly_saving_usd for d in decisions if d.allowed)
    blocked_usd = sum(d.action.monthly_saving_usd for d in decisions if not d.allowed)
    console.print(
        f"Allowed by policy: ${allowed_usd:.2f}/mo; blocked: ${blocked_usd:.2f}/mo"
    )
    return 0


def _apply_simulate_unhealthy(provider, console: Console, resource_id: str | None) -> None:
    if not resource_id:
        return
    if hasattr(provider, "unhealthy"):
        provider.unhealthy.add(resource_id)
    else:
        console.print(
            "[yellow]--simulate-unhealthy ignored: this provider has no health simulation[/yellow]"
        )


def _cmd_run(
    provider,
    console: Console,
    policy: Policy,
    *,
    execute: bool,
    report_out: Path,
    simulate_unhealthy: str | None,
) -> int:
    _apply_simulate_unhealthy(provider, console, simulate_unhealthy)
    findings = run_detectors(provider)
    plan = build_plan(findings, provider)
    decisions = gate(plan, policy)
    result = execute_run(provider, decisions, dry_run=not execute)
    report = render_report(result, dry_run=not execute)
    for record in result.records:
        suffix = f" ({record.error})" if record.error else ""
        console.print(
            f"{record.action.finding.resource.id}: {record.status.value}{suffix}"
        )
    console.print(f"Monthly savings applied: ${result.executed_saving_usd:.2f}")
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(report, encoding="utf-8")
    console.print(f"Report written to {report_out}")
    return 0


def _make_llm_client():
    """Build the real Qwen client; returns (client, None) or (None, reason)."""
    settings = load_qwen_settings()
    if not settings.api_key:
        return None, "QWEN_API_KEY is not configured"
    try:
        return QwenClient(settings), None
    except LLMError as exc:
        return None, str(exc)


def _print_agent_event(console: Console, event: dict) -> None:
    if event["role"] == "assistant" and "tool_calls" in event:
        for call in event["tool_calls"]:
            console.print(f"[dim]-> {call['name']}({call['arguments']})[/dim]")
    elif event["role"] == "tool":
        try:
            parsed = json.loads(event["result"])
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(parsed, dict):
            return
        if parsed.get("accepted") is True:
            console.print("[green]+ proposal accepted[/green]")
        elif parsed.get("accepted") is False:
            console.print(f"[red]- proposal rejected: {parsed.get('error', '')}[/red]")


def _save_transcript(directory: Path, agent_result: AgentResult, console: Console) -> None:
    if not agent_result.transcript:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"agent-transcript-{stamp}.json"
    payload = {
        "narrative": agent_result.narrative,
        "degraded": agent_result.degraded,
        "prompt_tokens": agent_result.prompt_tokens,
        "completion_tokens": agent_result.completion_tokens,
        "events": list(agent_result.transcript),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print(f"Transcript written to {path}")


def _finish_run(provider, console, decisions, agent_result, report_out, *, dry_run):
    result = execute_run(provider, decisions, dry_run=dry_run)
    for record in result.records:
        suffix = f" ({record.error})" if record.error else ""
        console.print(
            f"{record.action.finding.resource.id}: {record.status.value}{suffix}"
        )
    console.print(f"Monthly savings applied: ${result.executed_saving_usd:.2f}")
    report = render_report(result, dry_run=dry_run, narrative=agent_result.narrative)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(report, encoding="utf-8")
    _save_transcript(report_out.parent, agent_result, console)
    console.print(f"Report written to {report_out}")
    return 0


def _cmd_agent(
    provider,
    console: Console,
    policy: Policy,
    *,
    auto: bool,
    report_out: Path,
    simulate_unhealthy: str | None,
    max_tool_calls: int,
) -> int:
    _apply_simulate_unhealthy(provider, console, simulate_unhealthy)

    detector_findings = run_detectors(provider)
    _print_warnings(provider, console)
    client, problem = _make_llm_client()
    if client is None:
        console.print(
            f"[yellow]LLM unavailable ({problem}); continuing detector-only.[/yellow]"
        )
        agent_result = AgentResult(
            findings=(),
            narrative="(LLM unavailable - detector-only run)",
            transcript=(),
            degraded=True,
            degraded_reason=problem,
        )
    else:
        console.print("[bold]Agent investigating...[/bold]")
        agent_result = investigate(
            provider,
            detector_findings,
            client,
            max_tool_calls=max_tool_calls,
            on_event=lambda event: _print_agent_event(console, event),
        )
        if agent_result.degraded:
            console.print(
                f"[yellow]LLM degraded mid-run ({agent_result.degraded_reason}); "
                "using partial results.[/yellow]"
            )

    findings = detector_findings + list(agent_result.findings)
    plan = build_plan(findings, provider)
    decisions = gate(plan, policy)
    console.print(_plan_table(decisions))
    console.print(f"\n[bold]Agent narrative:[/bold] {agent_result.narrative}\n")

    if not auto:
        try:
            answer = input("Apply this plan? [y/N] ").strip().lower()
        except EOFError:
            answer = ""  # non-interactive stdin: treat as "no", never crash
        if answer not in ("y", "yes"):
            console.print("Plan not applied.")
            return _finish_run(
                provider, console, decisions, agent_result, report_out, dry_run=True
            )
    return _finish_run(
        provider, console, decisions, agent_result, report_out, dry_run=False
    )


def _force_utf8_stdio() -> None:
    """Tolerate any Unicode the model emits.

    The agent echoes the model's tool arguments to the console, and the model
    happily writes characters like ``->`` as the arrow ``→``. Windows
    consoles default to a legacy codepage (e.g. cp1251) that raises
    UnicodeEncodeError on such characters; reconfiguring to UTF-8 with
    ``errors="replace"`` makes printing safe everywhere.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # already-wrapped or non-reconfigurable stream: leave it


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args(argv)
    console = Console(width=160)
    try:
        provider = make_provider(args.provider)
    except CloudError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    if args.command == "scan":
        return _cmd_scan(provider, console)
    if args.command == "plan":
        policy = Policy(
            max_blast_radius=args.max_blast,
            allow_irreversible=args.allow_irreversible,
        )
        return _cmd_plan(provider, console, policy)
    if args.command == "run":
        policy = Policy(
            max_blast_radius=args.max_blast,
            allow_irreversible=args.allow_irreversible,
        )
        return _cmd_run(
            provider,
            console,
            policy,
            execute=args.execute,
            report_out=args.report_out,
            simulate_unhealthy=args.simulate_unhealthy,
        )
    policy = Policy(
        max_blast_radius=args.max_blast,
        allow_irreversible=args.allow_irreversible,
        block_llm_proposed=args.auto,
    )
    return _cmd_agent(
        provider,
        console,
        policy,
        auto=args.auto,
        report_out=args.report_out,
        simulate_unhealthy=args.simulate_unhealthy,
        max_tool_calls=args.max_tool_calls,
    )


if __name__ == "__main__":
    raise SystemExit(main())
