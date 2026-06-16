"""Cloud provider port. The mock and the future Alibaba adapter both implement this."""
from __future__ import annotations

from typing import Protocol

from steward.models import Metrics, Resource


class CloudError(Exception):
    """Raised by providers when a cloud operation fails."""


class CloudProvider(Protocol):
    # -- read ---------------------------------------------------------------
    def list_resources(self) -> list[Resource]: ...

    def get_resource(self, resource_id: str) -> Resource | None: ...

    def get_metrics(self, resource_id: str) -> Metrics | None: ...

    # -- mutations (raise CloudError on failure) -----------------------------
    def resize_instance(self, instance_id: str, target_instance_type: str) -> None: ...

    def release_eip(self, eip_id: str) -> None: ...

    def delete_disk(self, disk_id: str) -> None: ...

    def delete_snapshot(self, snapshot_id: str) -> None: ...

    def set_oss_storage_class(self, bucket_id: str, storage_class: str) -> None: ...

    def create_snapshot(self, disk_id: str) -> str: ...

    def restore_disk(self, snapshot_id: str) -> str: ...

    # -- verification ---------------------------------------------------------
    def health_check(self, resource_id: str) -> bool: ...
