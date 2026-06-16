from steward.models import ExecutionRecord, ExecutionStatus, RunResult
from steward.report import render_report
from steward.testing import make_finding, make_planned, make_resource


def test_pipe_in_resource_name_does_not_break_table():
    planned = make_planned(make_finding(make_resource("d-1", name="weird|name")))
    rec = ExecutionRecord(planned, ExecutionStatus.EXECUTED)
    text = render_report(RunResult(records=(rec,)), dry_run=False)
    assert "weird\\|name" in text


def record(status, *, rid="d-1", saving=40.0, reasons=(), error=None):
    planned = make_planned(make_finding(make_resource(rid), saving=saving))
    return ExecutionRecord(planned, status, reasons=tuple(reasons), error=error)


def test_dry_run_report_says_no_changes():
    result = RunResult(records=(record(ExecutionStatus.DRY_RUN),))
    text = render_report(result, dry_run=True)
    assert "Dry run" in text
    assert "no changes were made" in text


def test_execute_report_totals_applied_savings():
    result = RunResult(
        records=(
            record(ExecutionStatus.EXECUTED, rid="d-1", saving=40.0),
            record(ExecutionStatus.EXECUTED, rid="d-2", saving=2.5),
        )
    )
    text = render_report(result, dry_run=False)
    assert "**Monthly savings applied:** $42.50" in text
    assert "| d-1 (`d-1`) |" in text


def test_blocked_and_rolled_back_actions_are_explained():
    result = RunResult(
        records=(
            record(
                ExecutionStatus.BLOCKED,
                rid="i-prod",
                reasons=("protected by tag env=production",),
            ),
            record(
                ExecutionStatus.ROLLED_BACK,
                rid="i-stage",
                error="post-execution health check failed for i-stage; action rolled back",
            ),
        )
    )
    text = render_report(result, dry_run=False)
    assert "protected by tag env=production" in text
    assert "health check failed" in text
    assert "ROLLED BACK" in text


def test_report_includes_evidence_section():
    result = RunResult(records=(record(ExecutionStatus.EXECUTED),))
    text = render_report(result, dry_run=False)
    assert "## Why each action was proposed" in text
    assert "test evidence" in text


def test_report_explains_blast_reasons():
    result = RunResult(records=(record(ExecutionStatus.EXECUTED),))
    text = render_report(result, dry_run=False)
    assert "blast: test" in text


def test_rollback_failed_is_loud():
    result = RunResult(
        records=(
            record(
                ExecutionStatus.ROLLBACK_FAILED,
                rid="d-9",
                error=(
                    "post-execution health check failed for i-1 AND rollback "
                    "failed (resize API down); MANUAL INTERVENTION REQUIRED"
                ),
            ),
        )
    )
    text = render_report(result, dry_run=False)
    assert "MANUAL INTERVENTION" in text
    assert "ROLLBACK FAILED" in text


def test_report_includes_agent_narrative_when_provided():
    result = RunResult(records=(record(ExecutionStatus.EXECUTED),))
    text = render_report(result, dry_run=False, narrative="I reviewed 11 resources.")
    assert "## Agent narrative" in text
    assert "I reviewed 11 resources." in text


def test_report_omits_narrative_section_by_default():
    result = RunResult(records=(record(ExecutionStatus.EXECUTED),))
    assert "Agent narrative" not in render_report(result, dry_run=False)


def test_report_shows_cost_footnote_for_estimated_resources():
    planned = make_planned(
        make_finding(make_resource("i-1", cost_source="estimated"))
    )
    rec = ExecutionRecord(planned, ExecutionStatus.EXECUTED)
    text = render_report(RunResult(records=(rec,)), dry_run=False)
    assert "not from actual billing data" in text


def test_report_no_footnote_when_all_exact():
    planned = make_planned(make_finding(make_resource("i-1")))  # default exact
    rec = ExecutionRecord(planned, ExecutionStatus.EXECUTED)
    text = render_report(RunResult(records=(rec,)), dry_run=False)
    assert "not from actual billing data" not in text
