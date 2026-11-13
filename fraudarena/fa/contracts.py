"""Owner: M1. Frozen at H1 — Event, State, Rule, Decision (docs/FraudArena_Phase1_Plan.pdf section 4).

Rules are data, not code: a Rule is a JSON-serializable AND of simple feature
comparisons. This is what lets the defender propose patches later and the
verifier replay them safely. Never evaluate free-form Python/LLM-written
expressions as rules.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EventType = Literal["login", "device_add", "payee_add", "pay", "cashout"]
RuleAction = Literal["hold", "block"]
DecisionAction = Literal["allow", "hold", "block"]
Op = Literal["<", "<=", ">", ">=", "=="]

MAX_CONDITIONS = 4

# The 12 features computed by fa/core/features.py::compute_features. Any rule
# condition naming a feature outside this set is rejected by the rule loader.
ALLOWED_FEATURES = frozenset({
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
})


class Event(BaseModel):
    """One inbound action. ts is simulated seconds, never wall-clock time."""

    model_config = ConfigDict(frozen=True)

    id: str
    ts: int = Field(ge=0)
    account: str
    type: EventType
    amount: float = Field(ge=0)
    payee: str | None = None
    device: str | None = None
    channel: str | None = None


class AccountState(BaseModel):
    """State for a single account, before the current event is applied."""

    balance: float = 0.0
    avg_30d: float = 0.0
    payees: dict[str, int] = Field(default_factory=dict)  # payee_id -> first_seen_ts
    devices: dict[str, int] = Field(default_factory=dict)  # device_id -> first_seen_ts
    recent_pays: list[tuple[int, float, str]] = Field(default_factory=list)  # (ts, amount, payee)


class State(BaseModel):
    """Whole-world state: one AccountState per account, keyed by account id."""

    accounts: dict[str, AccountState] = Field(default_factory=dict)

    def account(self, account_id: str) -> AccountState:
        """Return the account's state, creating a fresh one if unseen."""
        return self.accounts.setdefault(account_id, AccountState())


class Condition(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature: str
    op: Op
    value: float

    @model_validator(mode="after")
    def _check_feature(self) -> "Condition":
        if self.feature not in ALLOWED_FEATURES:
            raise ValueError(f"unknown feature: {self.feature!r}")
        return self


class Rule(BaseModel):
    """A rule fires when every condition in `when` is true (AND)."""

    model_config = ConfigDict(frozen=True)

    id: str
    action: RuleAction
    when: list[Condition] = Field(min_length=1, max_length=MAX_CONDITIONS)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    action: DecisionAction
    rule_id: str | None = None
    version: int
    features: dict[str, float]
