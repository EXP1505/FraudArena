"""Owner: M1. Frozen at H1:00 per docs/TIMELINE.md section 3.

Event, Rule, Cond, RuleSet, Decision, Plan, Step, Trace, GateResult,
LedgerRecord, FEATURES, plus State/AccountState (needed by M3's
state.new_state() -> State).

Rules are data, not code: a Rule is a JSON-serializable AND of simple
feature comparisons (Cond). This is what lets the defender propose patches
later and the verifier replay them safely. Never evaluate free-form
Python/LLM-written expressions as rules.

Money is integer paise. Time is integer simulated seconds. Never call
time.time() inside fa/.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EventType = Literal["login", "add_payee", "payment", "cashout"]
RuleAction = Literal["hold", "block"]
DecisionAction = Literal["allow", "hold", "block"]
Op = Literal["<", "<=", ">", ">=", "=="]
Playbook = Literal["P1", "P2", "P3"]
Actor = Literal["victim", "mule"]
GateName = Literal["G1", "G2", "G3", "G4", "G5", "G6"]

MAX_CONDITIONS = 4

# The 12 features computed by fa/core/features.py::compute_features, in the
# agreed order (docs/FraudArena_Phase1_Plan.pdf section 5). Any rule
# condition naming a feature outside this set is rejected by the rule loader.
FEATURES: tuple[str, ...] = (
    "amount_ratio_30d",
    "payee_age_h",
    "device_changed_24h",
    "n_pay_1h",
    "n_pay_24h",
    "sum_1h",
    "sum_24h",
    "sum_newpayee_1h",
    "fan_out_1h",
    "r_fan_in_24h",
    "r_passthrough_1h",
    "hour_of_day",
    "night_flag",
)


# ---------------------------------------------------------------------------
# Simulator contracts (types; M3 owns the functions that build/mutate these)
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """One inbound action. ts is simulated seconds, never wall-clock time."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    ts: int = Field(ge=0)
    type: EventType
    account: str
    device: str | None = None
    payee: str | None = None
    amount: int = Field(ge=0, default=0)  # integer paise
    channel: str | None = None


class AccountState(BaseModel):
    """State for a single account, before the current event is applied."""

    balance: int = 0  # paise
    avg_30d: float = 0.0
    payees: dict[str, int] = Field(default_factory=dict)  # payee_id -> first_seen_ts
    devices: dict[str, int] = Field(default_factory=dict)  # device_id -> first_seen_ts
    recent_pays: list[tuple[int, int, str]] = Field(default_factory=list)  # (ts, amount, payee)


class State(BaseModel):
    """Whole-world state: one AccountState per account, keyed by account id."""

    accounts: dict[str, AccountState] = Field(default_factory=dict)

    def account(self, account_id: str) -> AccountState:
        """Return the account's state, creating a fresh one if unseen."""
        return self.accounts.setdefault(account_id, AccountState())


# ---------------------------------------------------------------------------
# Rule contracts
# ---------------------------------------------------------------------------


class Cond(BaseModel):
    model_config = ConfigDict(frozen=True)

    f: str
    op: Op
    v: float | bool

    @model_validator(mode="after")
    def _check_feature(self) -> "Cond":
        if self.f not in FEATURES:
            raise ValueError(f"unknown feature: {self.f!r}")
        return self


class Rule(BaseModel):
    """A rule fires when every condition in `when` is true (AND)."""

    model_config = ConfigDict(frozen=True)

    id: str
    action: RuleAction
    when: list[Cond] = Field(min_length=1, max_length=MAX_CONDITIONS)
    rationale: str = ""
    evidence: dict = Field(default_factory=dict)
    source: str = "hand"  # hand | mined | llm
    added_in: str = "v1"


class RuleSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    rules: list[Rule]


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    decision: DecisionAction
    fired: list[str] = Field(default_factory=list)
    version: str
    latency_us: float = 0.0


# ---------------------------------------------------------------------------
# Attack-plan contracts
# ---------------------------------------------------------------------------


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)

    t: int
    actor: Actor
    act: str
    payee: str | None = None
    device: str | None = None
    amount: int | None = None


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str
    playbook: Playbook
    seed: int
    params: dict = Field(default_factory=dict)
    steps: list[Step]


class Trace(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str
    steps: list[tuple[Step, dict[str, float], Decision]]
    loss_through: int = 0
    missed_step: int | None = None


# ---------------------------------------------------------------------------
# Verifier / release / ledger contracts
# ---------------------------------------------------------------------------


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate: GateName
    passed: bool
    reason: str = ""
    evidence: dict = Field(default_factory=dict)


class LedgerRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    ts: int
    action: str
    payload: dict
    prev_hash: str
    hash: str
    sig: str
