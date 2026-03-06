import json
import os
import time
from dataclasses import dataclass, field
from filelock import FileLock, Timeout


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


def _env_float(key: str, default: float) -> float:
    """Read a float env var with a default."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    """Read an int env var with a default."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


class BudgetCoordinator:
    """
    Cross-process budget coordinator for sports and general pipelines.
    Uses filelock to prevent race conditions when both pipelines run concurrently.
    """

    def __init__(self, wallet_balance: float) -> None:
        self.wallet_balance = max(0.0, float(wallet_balance))

        # Core config
        budget_fraction = _env_float("SPORTS_BUDGET_FRACTION", 0.30)
        self.sports_budget = round(self.wallet_balance * budget_fraction, 10)
        self.general_budget = round(self.wallet_balance - self.sports_budget, 10)
        self.min_wallet_usd = _env_float("SPORTS_MIN_WALLET_USD", 50.0)
        self.lock_timeout = _env_int("SPORTS_BUDGET_LOCK_TIMEOUT_SECONDS", 5)
        self.lock_path = os.environ.get(
            "SPORTS_BUDGET_LOCK_PATH", "/tmp/polyagents_budget.lock"
        )
        self.json_path = os.environ.get(
            "SPORTS_BUDGET_FILE_PATH", "/tmp/polyagents_budget.json"
        )

        # Parse per-sport caps from SPORTS_CAP_{LEAGUE} env vars
        self._per_sport_caps: dict[str, float] = {}
        for key, val in os.environ.items():
            if key.startswith("SPORTS_CAP_"):
                league = key[len("SPORTS_CAP_") :]
                try:
                    self._per_sport_caps[league] = float(val)
                except ValueError:
                    pass

    def allocate_budget(self) -> dict:
        """Write initial budget allocation to JSON file under filelock."""
        per_sport = {
            league: round(frac * self.sports_budget, 10)
            for league, frac in self._per_sport_caps.items()
        }
        data = {
            "sports": self.sports_budget,
            "general": self.general_budget,
            "per_sport": per_sport,
            "wallet_balance": self.wallet_balance,
            "timestamp": time.time(),
        }
        self._write_budget_file(data)
        return data

    def get_sports_budget(self) -> float:
        """Return remaining sports budget from JSON file."""
        data = self._read_budget_file()
        return float(data.get("sports", self.sports_budget))

    def get_general_budget(self) -> float:
        """Return remaining general budget from JSON file."""
        data = self._read_budget_file()
        return float(data.get("general", self.general_budget))

    def can_spend_sports(self, amount: float, wallet_balance: float) -> bool:
        """Check if sports pipeline can spend amount given current state."""
        if wallet_balance < self.min_wallet_usd:
            return False
        remaining = self.get_sports_budget()
        return float(amount) <= remaining

    def get_sport_cap(self, league: str) -> float:
        """
        Return per-sport cap for a given league.
        Configured leagues: cap_fraction * sports_budget.
        Unconfigured leagues: equal share of remainder.
        """
        sports_budget = self.get_sports_budget()
        if league in self._per_sport_caps:
            return round(self._per_sport_caps[league] * sports_budget, 10)

        # Unconfigured: share the remaining fraction equally
        configured_sum = sum(self._per_sport_caps.values())
        remaining_fraction = max(0.0, 1.0 - configured_sum)
        num_unconfigured = 1  # caller asks for one league; remainder goes to it
        return round(remaining_fraction / num_unconfigured * sports_budget, 10)

    def record_sports_trade(self, amount: float, league: str) -> None:
        """Decrement sports budget (and per-sport allocation) under filelock."""
        lock = FileLock(self.lock_path, timeout=self.lock_timeout)
        with lock:
            data = self._read_budget_file_unlocked()
            data["sports"] = round(
                float(data.get("sports", self.sports_budget)) - float(amount), 10
            )
            per_sport = data.get("per_sport", {})
            if league in per_sport:
                per_sport[league] = round(float(per_sport[league]) - float(amount), 10)
            data["per_sport"] = per_sport
            self._write_budget_file_unlocked(data)

    def _read_budget_file(self) -> dict:
        """Read budget JSON under lock."""
        lock = FileLock(self.lock_path, timeout=self.lock_timeout)
        with lock:
            return self._read_budget_file_unlocked()

    def _read_budget_file_unlocked(self) -> dict:
        """Read budget JSON without acquiring lock (caller must hold lock)."""
        if not os.path.exists(self.json_path):
            return {
                "sports": self.sports_budget,
                "general": self.general_budget,
                "per_sport": {},
                "wallet_balance": self.wallet_balance,
                "timestamp": time.time(),
            }
        with open(self.json_path) as f:
            return json.load(f)

    def _write_budget_file(self, data: dict) -> None:
        """Write budget JSON under lock."""
        lock = FileLock(self.lock_path, timeout=self.lock_timeout)
        with lock:
            self._write_budget_file_unlocked(data)

    def _write_budget_file_unlocked(self, data: dict) -> None:
        """Write budget JSON without acquiring lock (caller must hold lock)."""
        with open(self.json_path, "w") as f:
            json.dump(data, f)
