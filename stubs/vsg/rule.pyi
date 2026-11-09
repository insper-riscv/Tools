from typing import Any

from vsg.violation import New

class Rule:
    name: str
    identifier: str
    unique_id: str
    phase: int
    fixable: bool
    def __init__(self) -> None: ...
    def add_violation(self, violation: New) -> None: ...
    def analyze(self, oFile: Any) -> None: ...
