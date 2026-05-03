from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CitizenMode(StrEnum):
    MINE = "MINE"
    SYNC = "SYNC"
    SLEEP = "SLEEP"


class StatusEffect(StrEnum):
    JAILED = "JAILED"
    JAMMED = "JAMMED"
    SURVEILLED = "SURVEILLED"
    MOST_WANTED = "MOST_WANTED"
    GHOSTED = "GHOSTED"
    PROTECTED = "PROTECTED"


class CitizenAction(StrEnum):
    SNIFF = "SNIFF"
    JAM_SCAN = "JAM_SCAN"
    DECOY_SIGNAL = "DECOY_SIGNAL"
    COVER_TRACKS = "COVER_TRACKS"


class MayorAction(StrEnum):
    JAIL = "JAIL"
    JAM = "JAM"
    SURVEIL = "SURVEIL"
    CURFEW = "CURFEW"
    STK_DRAIN = "STK_DRAIN"
    MOST_WANTED = "MOST_WANTED"


class JobKind(StrEnum):
    CITIZEN_DECISION = "CITIZEN_DECISION"
    MAYOR_DECREE = "MAYOR_DECREE"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class DecisionKind(StrEnum):
    ACTION = "ACTION"
    MODE_CHANGE = "MODE_CHANGE"
    HOLD = "HOLD"


@dataclass
class TimedStatus:
    effect: StatusEffect
    expires_at: float


@dataclass
class Citizen:
    citizen_id: str
    behavior: str = "aggressive"
    mode: CitizenMode = CitizenMode.MINE
    queued_mode: CitizenMode | None = None
    stk: float = 2500.0
    shiva: float = 35.0
    trace: float = 10.0
    last_decision_at: float = -999.0
    action_cooldown_until: float = 0.0
    statuses: list[TimedStatus] = field(default_factory=list)

    def has_status(self, effect: StatusEffect, now: float) -> bool:
        return any(status.effect == effect and status.expires_at > now for status in self.statuses)

    def active_statuses(self, now: float) -> list[TimedStatus]:
        return [status for status in self.statuses if status.expires_at > now]


@dataclass
class CityState:
    game_id: str
    season_seconds: int
    started_at: float = 0.0
    now: float = 0.0
    heat: float = 45.0
    server_scan_jammed_until: float = 0.0
    mayor_next_tick_at: float = 10.0
    citizens: dict[str, Citizen] = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        return max(0.0, self.now - self.started_at)

    @property
    def game_hour(self) -> float:
        return min(72.0, (self.elapsed / self.season_seconds) * 72.0)

    @property
    def is_finished(self) -> bool:
        return self.elapsed >= self.season_seconds or self.heat <= 0.0 or self.heat >= 100.0


@dataclass
class CitizenDecision:
    citizen_id: str
    kind: DecisionKind
    action: CitizenAction | None = None
    mode: CitizenMode | None = None
    rationale: str = ""


@dataclass
class MayorDecree:
    action: MayorAction
    targets: list[str]
    rationale: str
    duration_seconds: int = 60


@dataclass
class GameEvent:
    event_id: str
    tick: int
    game_hour: float
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    public: bool = True


@dataclass
class DossierTarget:
    citizen_id: str
    action: CitizenAction
    p_catch: float
    trace: float
    shiva: float
    evidence: str


@dataclass
class Dossier:
    dossier_id: str
    created_at: float
    heat: float
    targets: list[DossierTarget]


def to_plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return to_plain(asdict(value))
    return value
