from __future__ import annotations

from enum import IntEnum


class Condition(IntEnum):
    """Active cumulative experimental conditions."""

    N0 = 0
    R1 = 1
    R2 = 2
    R3 = 3
    R2_C = 4
    R2_V = 5

    @classmethod
    def parse(cls, value: str | "Condition") -> "Condition":
        if isinstance(value, cls):
            return value
        try:
            return cls[str(value).strip().upper().replace("+", "_")]
        except KeyError as exc:
            allowed = ", ".join(item.name for item in cls)
            raise ValueError(f"unknown condition {value!r}; expected one of {allowed}") from exc

    def enables(self, component: str) -> bool:
        enabled = {
            "runtime_communication": {self.R1, self.R2, self.R3, self.R2_C, self.R2_V},
            "runtime_routing": {self.R2, self.R3, self.R2_C, self.R2_V},
            "work_contracts": {self.R3, self.R2_C},
            "verifier": {self.R3, self.R2_V},
        }
        try:
            return self in enabled[component]
        except KeyError as exc:
            raise ValueError(f"unknown RAC component {component!r}") from exc

    def features(self) -> dict[str, bool]:
        return {name: self.enables(name) for name in
                ("runtime_communication", "runtime_routing", "work_contracts", "verifier")}
