import time
from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    amount: float
    market_id: int
    outcome: str
    timestamp: float = field(default_factory=time.time)


class SessionBudgetManager:
    def __init__(self, total_budget: float) -> None:
        self.total_budget = max(0.0, float(total_budget))
        self.spent = 0.0
        self.trades: list[TradeRecord] = []

    def remaining(self) -> float:
        return max(0.0, self.total_budget - self.spent)

    def can_spend(self, amount: float) -> bool:
        return float(amount) <= self.remaining()

    def is_exhausted(self) -> bool:
        return self.remaining() <= 0.0

    def record_trade(self, amount: float, market_id: int, outcome: str) -> None:
        record = TradeRecord(amount=float(amount), market_id=market_id, outcome=outcome)
        self.trades.append(record)
        self.spent += record.amount

    def is_on_cooldown(self, market_id: int, cooldown_seconds: float) -> bool:
        now = time.time()
        for trade in reversed(self.trades):
            if trade.market_id == market_id:
                return (now - trade.timestamp) < cooldown_seconds
        return False

    def summary(self) -> str:
        return (
            f"Session budget: ${self.total_budget:.2f} | "
            f"Spent: ${self.spent:.2f} | "
            f"Remaining: ${self.remaining():.2f} | "
            f"{len(self.trades)} trades"
        )
