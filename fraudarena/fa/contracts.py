# Owner: M1. Frozen at H1. Event, State, Rule, Decision (see docs/FraudArena_Phase1_Plan.pdf section 4).
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

class Condition(BaseModel):
    f: str  # feature name
    op: Literal["<", "<=", ">", ">=", "=="]
    v: Any  # threshold or value

class Rule(BaseModel):
    id: str
    action: Literal["hold", "block"]
    when: List[Condition] = Field(..., max_length=4)
    rationale: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    source: Optional[str] = "baseline"
    added_in: Optional[str] = "v1"

class Event(BaseModel):
    id: Optional[str] = None
    event_id: Optional[str] = None
    ts: int  # simulated clock in integer seconds
    account: str
    type: str = "pay"  # login | device_add | payee_add | pay | cashout | payment
    amount: Optional[float] = 0.0  # paise
    payee: Optional[str] = None
    device: Optional[str] = None
    channel: Optional[str] = "upi"

    def model_post_init(self, __context: Any) -> None:
        if not self.event_id and self.id:
            self.event_id = self.id
        elif not self.id and self.event_id:
            self.id = self.event_id
        elif not self.id and not self.event_id:
            self.id = f"e-{self.ts}"
            self.event_id = self.id

class Decision(BaseModel):
    event_id: str
    action: Literal["allow", "hold", "block"]
    rule_id: Optional[str] = None
    version: int = 1
    features: Dict[str, Any] = Field(default_factory=dict)
    latency_us: Optional[int] = None

class AccountState(BaseModel):
    balance: float = 0.0
    avg_30d: float = 0.0
    payees: Dict[str, int] = Field(default_factory=dict)  # payee_id -> first_seen_ts
    devices: Dict[str, int] = Field(default_factory=dict)  # device_id -> first_seen_ts
    recent_pays: List[Tuple[int, float, str]] = Field(default_factory=list)  # (ts, amt, payee)

class State(BaseModel):
    accounts: Dict[str, AccountState] = Field(default_factory=dict)
    inflows: Dict[str, List[Tuple[int, str, float]]] = Field(default_factory=dict)  # payee -> (ts, sender, amt)
    outflows: Dict[str, List[Tuple[int, float]]] = Field(default_factory=dict)  # account -> (ts, amt)
