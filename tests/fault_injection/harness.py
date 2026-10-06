from __future__ import annotations

NAMED_BOUNDARIES = (
    "after_temp_write_before_file_fsync",
    "after_file_fsync_before_rename",
    "after_rename_before_parent_dir_fsync",
    "after_parent_dir_fsync_before_next_step",
    "before_revision_durable_write",
    "after_revision_durable_write",
    "before_mutation_committed_append",
    "after_mutation_committed_append",
    "before_effect_boundary_publish",
    "after_effect_boundary_publish",
    "after_external_effect_dispatch_before_terminal_result",
)

class InjectedCrash(RuntimeError):
    pass

class FaultInjector:
    def __init__(self, point: str | None = None):
        if point is not None and point not in NAMED_BOUNDARIES:
            raise ValueError("unknown fault point: " + point)
        self.point = point
        self.seen: list[str] = []

    def hit(self, point: str) -> None:
        if point not in NAMED_BOUNDARIES:
            raise ValueError("unregistered fault point: " + point)
        self.seen.append(point)
        if self.point == point:
            raise InjectedCrash(point)
