"""Safe execution engine: capture before-state, execute, verify, roll back.

Invariants:
- the before-state is captured before any mutation;
- DELETE_DISK takes a safety snapshot first, making it reversible;
- a failed post-execution health check rolls the action back (when possible)
  and halts the batch;
- a rollback that itself fails is recorded as ROLLBACK_FAILED (manual intervention
  required) rather than raising — the before-state is preserved in the record;
- any CloudError halts the batch; later actions are recorded as NOT_REACHED.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from steward.models import (
    ActionSpec,
    ActionType,
    ExecutionRecord,
    ExecutionStatus,
    GateDecision,
    RunResult,
)
from steward.providers.base import CloudError, CloudProvider

# -- before-state capture -----------------------------------------------------


def _capture_common(provider: CloudProvider, spec: ActionSpec) -> dict:
    resource = provider.get_resource(spec.resource_id)
    if resource is None:
        raise CloudError(f"resource disappeared before execution: {spec.resource_id}")
    return {
        "resource_id": resource.id,
        "attached_to": resource.attached_to,
        "spec": dict(resource.spec),
    }


def _capture_disk_delete(provider: CloudProvider, spec: ActionSpec) -> dict:
    state = _capture_common(provider, spec)
    # Safety net: snapshot the disk first so the delete is reversible.
    state["rollback_snapshot_id"] = provider.create_snapshot(spec.resource_id)
    return state


# -- execute -------------------------------------------------------------------


def _exec_resize(provider: CloudProvider, spec: ActionSpec) -> None:
    provider.resize_instance(spec.resource_id, spec.params["target_instance_type"])


def _exec_release_eip(provider: CloudProvider, spec: ActionSpec) -> None:
    provider.release_eip(spec.resource_id)


def _exec_delete_disk(provider: CloudProvider, spec: ActionSpec) -> None:
    provider.delete_disk(spec.resource_id)


def _exec_delete_snapshot(provider: CloudProvider, spec: ActionSpec) -> None:
    provider.delete_snapshot(spec.resource_id)


def _exec_change_oss_class(provider: CloudProvider, spec: ActionSpec) -> None:
    provider.set_oss_storage_class(
        spec.resource_id, spec.params["target_storage_class"]
    )


# -- rollback -------------------------------------------------------------------


def _rollback_resize(provider: CloudProvider, spec: ActionSpec, before: dict) -> None:
    provider.resize_instance(spec.resource_id, before["spec"]["instance_type"])


def _rollback_disk_delete(
    provider: CloudProvider, spec: ActionSpec, before: dict
) -> None:
    provider.restore_disk(before["rollback_snapshot_id"])


def _rollback_oss_class(
    provider: CloudProvider, spec: ActionSpec, before: dict
) -> None:
    provider.set_oss_storage_class(spec.resource_id, before["spec"]["storage_class"])


# -- verification targets ----------------------------------------------------------


def _verify_self(spec: ActionSpec, before: dict) -> str | None:
    return spec.resource_id


def _verify_parent(spec: ActionSpec, before: dict) -> str | None:
    return before.get("attached_to")


# -- handler registry ------------------------------------------------------------


@dataclass(frozen=True)
class _Handler:
    capture: Callable[[CloudProvider, ActionSpec], dict]
    execute: Callable[[CloudProvider, ActionSpec], None]
    rollback: Callable[[CloudProvider, ActionSpec, dict], None] | None  # None = irreversible
    verify_target: Callable[[ActionSpec, dict], str | None]


_HANDLERS: dict[ActionType, _Handler] = {
    ActionType.RESIZE_ECS: _Handler(
        _capture_common, _exec_resize, _rollback_resize, _verify_self
    ),
    ActionType.RELEASE_EIP: _Handler(
        _capture_common, _exec_release_eip, None, _verify_parent
    ),
    ActionType.DELETE_DISK: _Handler(
        _capture_disk_delete, _exec_delete_disk, _rollback_disk_delete, _verify_parent
    ),
    ActionType.DELETE_SNAPSHOT: _Handler(
        _capture_common, _exec_delete_snapshot, None, _verify_parent
    ),
    ActionType.CHANGE_OSS_CLASS: _Handler(
        _capture_common, _exec_change_oss_class, _rollback_oss_class, _verify_self
    ),
}


def is_reversible(action_type: ActionType) -> bool:
    return _HANDLERS[action_type].rollback is not None


# -- helpers -------------------------------------------------------------------


def _cleanup_safety_snapshot(provider: CloudProvider, before: dict) -> None:
    """Best-effort removal of a pre-delete safety snapshot whose action never completed.

    A snapshot that outlives a *successful* delete is the durable backup and is
    kept deliberately; one left behind by a failed delete is pure garbage.
    """
    snap_id = before.get("rollback_snapshot_id")
    if snap_id is None:
        return
    try:
        provider.delete_snapshot(snap_id)
    except CloudError:
        pass  # the FAILED record already reports the original error; never mask it


# -- main loop -----------------------------------------------------------------


def run(
    provider: CloudProvider, decisions: list[GateDecision], dry_run: bool = True
) -> RunResult:
    records: list[ExecutionRecord] = []
    halted = False
    for decision in decisions:
        planned = decision.action
        if not decision.allowed:
            records.append(
                ExecutionRecord(planned, ExecutionStatus.BLOCKED, reasons=decision.reasons)
            )
            continue
        if halted:
            records.append(
                ExecutionRecord(
                    planned,
                    ExecutionStatus.NOT_REACHED,
                    reasons=("batch halted by an earlier failure",),
                )
            )
            continue
        if dry_run:
            records.append(ExecutionRecord(planned, ExecutionStatus.DRY_RUN))
            continue

        handler = _HANDLERS[planned.action.type]
        try:
            before = handler.capture(provider, planned.action)
        except CloudError as exc:
            records.append(
                ExecutionRecord(planned, ExecutionStatus.FAILED, error=str(exc))
            )
            halted = True
            continue
        try:
            handler.execute(provider, planned.action)
        except CloudError as exc:
            _cleanup_safety_snapshot(provider, before)
            records.append(
                ExecutionRecord(
                    planned, ExecutionStatus.FAILED, before_state=before, error=str(exc)
                )
            )
            halted = True
            continue

        target = handler.verify_target(planned.action, before)
        if target is not None and not provider.health_check(target):
            if handler.rollback is None:
                records.append(
                    ExecutionRecord(
                        planned,
                        ExecutionStatus.FAILED,
                        before_state=before,
                        error=(
                            f"post-execution health check failed for {target}; "
                            "action is irreversible and could not be rolled back"
                        ),
                    )
                )
            else:
                try:
                    # Catch everything, not just CloudError: a rollback that
                    # escapes run() would lose the record of a mutated resource.
                    handler.rollback(provider, planned.action, before)
                except Exception as exc:  # noqa: BLE001 — last-resort boundary
                    records.append(
                        ExecutionRecord(
                            planned,
                            ExecutionStatus.ROLLBACK_FAILED,
                            before_state=before,
                            error=(
                                f"post-execution health check failed for {target} "
                                f"AND rollback failed ({exc}); "
                                "MANUAL INTERVENTION REQUIRED — before-state preserved"
                            ),
                        )
                    )
                else:
                    records.append(
                        ExecutionRecord(
                            planned,
                            ExecutionStatus.ROLLED_BACK,
                            before_state=before,
                            error=f"post-execution health check failed for {target}; action rolled back",
                        )
                    )
            halted = True
            continue

        records.append(
            ExecutionRecord(planned, ExecutionStatus.EXECUTED, before_state=before)
        )
    return RunResult(records=tuple(records))
