from steward.cli import main


def test_scan_lists_resources_and_findings(capsys):
    assert main(["scan"]) == 0
    out = capsys.readouterr().out
    assert "i-staging-app" in out
    assert "oss-archives" in out
    assert "Potential monthly saving: $561.50" in out


def test_plan_shows_gate_decisions(capsys):
    assert main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "i-prod-batch" in out
    assert "BLOCK" in out
    assert "ALLOW" in out


def test_run_is_dry_run_by_default(tmp_path, capsys):
    report = tmp_path / "report.md"
    assert main(["run", "--report-out", str(report)]) == 0
    out = capsys.readouterr().out
    assert "dry_run" in out
    assert "Monthly savings applied: $0.00" in out
    text = report.read_text(encoding="utf-8")
    assert "Dry run" in text


def test_run_execute_applies_allowed_actions(tmp_path, capsys):
    report = tmp_path / "report.md"
    assert (
        main(
            [
                "run",
                "--execute",
                "--max-blast",
                "4",
                "--allow-irreversible",
                "--report-out",
                str(report),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    # everything except the production-tagged resize is applied:
    # 9 + 6 + 6 + 58.5 + 44 + 18 + 280 = 421.5
    assert "Monthly savings applied: $421.50" in out
    assert "i-prod-batch: blocked" in out
    text = report.read_text(encoding="utf-8")
    assert "protected by tag env=production" in text


def test_plan_respects_policy_flags(capsys):
    assert main(["plan", "--max-blast", "4", "--allow-irreversible"]) == 0
    out = capsys.readouterr().out
    # with raised gates only the production-tagged resize stays blocked
    assert out.count("BLOCK") == 1
    assert "Allowed by policy: $421.50/mo; blocked: $140.00/mo" in out


def test_run_rollback_demo(tmp_path, capsys):
    report = tmp_path / "report.md"
    assert (
        main(
            [
                "run",
                "--execute",
                "--max-blast",
                "4",
                "--allow-irreversible",
                "--simulate-unhealthy",
                "i-staging-app",
                "--report-out",
                str(report),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "i-staging-app: rolled_back" in out
    # the staging resize ($280) was rolled back: 421.5 - 280 = 141.5
    assert "Monthly savings applied: $141.50" in out


from steward.llm.agent import AgentResult
from steward.models import ActionSpec, ActionType, Finding


def fake_agent_result(provider):
    eip = provider.get_resource("eip-prod")
    finding = Finding(
        kind="llm_release_eip",
        resource=eip,
        evidence="llm spotted this",
        monthly_saving_usd=3.0,
        action=ActionSpec(ActionType.RELEASE_EIP, "eip-prod"),
        source="llm",
    )
    return AgentResult(
        findings=(finding,),
        narrative="One extra saving beyond the detectors.",
        transcript=({"role": "assistant", "content": "done"},),
        prompt_tokens=123,
        completion_tokens=45,
    )


def patch_agent(monkeypatch):
    from steward import cli

    monkeypatch.setattr(cli, "_make_llm_client", lambda: (object(), None))
    monkeypatch.setattr(
        cli,
        "investigate",
        lambda provider, findings, client, **kwargs: fake_agent_result(provider),
    )


def test_agent_auto_blocks_llm_proposals(tmp_path, monkeypatch, capsys):
    patch_agent(monkeypatch)
    report = tmp_path / "r.md"
    assert (
        main(
            [
                "agent",
                "--auto",
                "--max-blast",
                "4",
                "--allow-irreversible",
                "--report-out",
                str(report),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "eip-prod: blocked" in out
    assert "Monthly savings applied: $421.50" in out  # detector findings only
    text = report.read_text(encoding="utf-8")
    assert "interactive approval" in text
    assert "One extra saving beyond the detectors." in text
    transcripts = list(tmp_path.glob("agent-transcript-*.json"))
    assert len(transcripts) == 1


def test_agent_interactive_yes_executes_llm_proposal(tmp_path, monkeypatch, capsys):
    patch_agent(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    report = tmp_path / "r.md"
    assert (
        main(
            [
                "agent",
                "--max-blast",
                "4",
                "--allow-irreversible",
                "--report-out",
                str(report),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "eip-prod: executed" in out
    assert "Monthly savings applied: $424.50" in out  # 421.50 + 3.00


def test_agent_interactive_no_leaves_account_untouched(tmp_path, monkeypatch, capsys):
    patch_agent(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    report = tmp_path / "r.md"
    assert (
        main(
            [
                "agent",
                "--max-blast",
                "4",
                "--allow-irreversible",
                "--report-out",
                str(report),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Plan not applied." in out
    assert "Dry run" in report.read_text(encoding="utf-8")


def test_agent_degrades_without_api_key(tmp_path, monkeypatch, capsys):
    from steward import cli

    monkeypatch.setattr(
        cli, "_make_llm_client", lambda: (None, "QWEN_API_KEY is not configured")
    )
    report = tmp_path / "r.md"
    assert main(["agent", "--auto", "--report-out", str(report)]) == 0
    out = capsys.readouterr().out
    assert "detector-only" in out


def test_agent_interactive_eof_does_not_crash(tmp_path, monkeypatch, capsys):
    patch_agent(monkeypatch)

    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    report = tmp_path / "r.md"
    assert (
        main(["agent", "--max-blast", "4", "--allow-irreversible", "--report-out", str(report)])
        == 0
    )
    out = capsys.readouterr().out
    assert "Plan not applied." in out
    assert "Dry run" in report.read_text(encoding="utf-8")


def test_print_agent_event_narrates_accepted_and_rejected(capsys):
    from rich.console import Console

    from steward import cli

    console = Console()
    cli._print_agent_event(
        console, {"role": "tool", "name": "propose_action", "result": '{"accepted": true}'}
    )
    cli._print_agent_event(
        console,
        {
            "role": "tool",
            "name": "propose_action",
            "result": '{"accepted": false, "error": "no such resource: \'i-bad\'"}',
        },
    )
    out = capsys.readouterr().out
    assert "proposal accepted" in out
    assert "proposal rejected" in out
    assert "i-bad" in out


def test_print_agent_event_tolerates_non_ascii_arguments():
    import io

    from rich.console import Console

    from steward import cli

    # The model emits characters like the arrow in its arguments. A console whose
    # stream cannot natively encode them must not crash when it uses
    # errors="replace" (what _force_utf8_stdio guarantees in production).
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1251", errors="replace")
    console = Console(file=stream, legacy_windows=False, width=80)
    event = {
        "role": "assistant",
        "tool_calls": [
            {"name": "propose_action", "arguments": '{"evidence": "Standard → IA"}'}
        ],
    }
    cli._print_agent_event(console, event)  # must not raise UnicodeEncodeError
    stream.flush()
    assert raw.getvalue()  # something was written


def test_force_utf8_stdio_is_safe_on_non_reconfigurable_streams(monkeypatch):
    import io

    from steward import cli

    monkeypatch.setattr("sys.stdout", io.StringIO())
    monkeypatch.setattr("sys.stderr", io.StringIO())
    cli._force_utf8_stdio()  # StringIO has no reconfigure -> swallowed, no raise


def test_make_provider_alibaba_is_lazy_and_wired(monkeypatch):
    from steward import cli

    built = {}

    class FakeAlibaba:
        def __init__(self, config, *, allow_destructive):
            built["allow_destructive"] = allow_destructive

    monkeypatch.setattr(cli, "_build_alibaba_provider", lambda: FakeAlibaba("cfg", allow_destructive=False))
    provider = cli.make_provider("alibaba")
    assert isinstance(provider, FakeAlibaba)


def test_unknown_provider_errors():
    from steward import cli

    import pytest

    with pytest.raises(SystemExit):
        cli.make_provider("gcp")


def test_print_warnings_surfaces_provider_warnings(capsys):
    from rich.console import Console

    from steward import cli

    class P:
        last_warnings = ["oss listing failed: UserDisable"]

    cli._print_warnings(P(), Console())
    out = capsys.readouterr().out
    assert "oss listing failed" in out
    assert "warning" in out


def test_print_warnings_noop_for_provider_without_attribute(capsys):
    from rich.console import Console

    from steward import cli

    cli._print_warnings(object(), Console())  # mock provider has no last_warnings
    assert capsys.readouterr().out == ""
