"""Canonical v0.1 diagnostic registry (stdlib only).

Mirrors the error registry in the v0.1 core document. A None code on a
Diagnostic means generic parse rejection. E-SHARE-01 and E-GC-01 are reserved
with no producer in M5; fetch and oracle producers arrived with the M5 CLI.
"""

from dataclasses import dataclass

E_SEAL_01 = "E-SEAL-01"
E_REGION_01 = "E-REGION-01"
E_MOVE_01 = "E-MOVE-01"
E_TYPE_01 = "E-TYPE-01"
E_DISCARD_01 = "E-DISCARD-01"
E_TASK_01 = "E-TASK-01"
E_CHAN_01 = "E-CHAN-01"
E_SHARE_01 = "E-SHARE-01"  # Reserved: no producer in M5.
E_GC_01 = "E-GC-01"  # Reserved: no producer in M5.
E_FETCH_01 = "E-FETCH-01"
E_SEED_01 = "E-SEED-01"
E_DAEMON_01 = "E-DAEMON-01"
E_CANCEL_01 = "E-CANCEL-01"
E_NONDET_01 = "E-NONDET-01"
W_CONTRACT_01 = "W-CONTRACT-01"
W_TERM_01 = "W-TERM-01"


@dataclass
class Diagnostic:
    """One driver finding. A None code means generic parse rejection."""

    code: str | None
    lineno: int
    message: str

    def render(self) -> str:
        if self.code is None:
            return f"parse error at line {self.lineno}: {self.message}"
        return f"{self.code} at line {self.lineno}: {self.message}"
