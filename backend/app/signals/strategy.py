"""Versioned strategy configurations. A signal stores a full snapshot of the config it used plus its hash,
so changing a strategy never rewrites old signals."""
import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    version: str
    profile: str                       # "scalp" | "day" | "swing"
    timeframe: str
    htf: str                           # higher timeframe for context
    min_bars: int = 200
    max_staleness_intervals: float = 2.0   # last closed candle must be at most this many intervals old
    max_gaps: int = 2
    adx_trend_min: float = 20.0
    atr_pct_volatile: float = 6.0      # ATR as % of price above this → "volatile" regime, no trade
    zone_lookback: int = 60            # OB/FVG must be created within this many bars
    zone_max_dist_atr: float = 1.5     # price may be at most this many ATRs from the zone
    stop_buffer_atr: float = 0.25
    min_rr: float = 1.5                # net reward:risk to TP1 after costs
    min_score: int = 60
    expiry_bars: int = 12
    fee_rate: dict = field(default_factory=lambda: {"spot": 0.001, "futures": 0.0005})   # per side, taker
    slippage: float = 0.0005           # per side
    funding_extreme: float = 0.0005    # per funding period
    # v1.1 research options — defaults reproduce v1.0.0 exactly
    stop_min_atr: float = 0.0          # stop at least this many ATRs from the entry-zone midpoint
    htf_required: bool = False         # require the higher-timeframe trend to agree
    target_mode: str = "liquidity"     # "liquidity" or "r_multiple"
    r_targets: tuple = (1.5, 2.5, 3.5) # used when target_mode == "r_multiple"
    min_risk_cost_ratio: float = 0.0   # risk per unit must be ≥ this × round-trip cost

    def snapshot(self) -> dict:
        return asdict(self)

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()[:16]


SMC_TREND_PULLBACK_V1 = StrategyConfig(name="smc_trend_pullback", version="1.0.0", profile="day", timeframe="1H", htf="4H")

PROFILES = {
    "day": SMC_TREND_PULLBACK_V1,
    "swing": StrategyConfig(name="smc_trend_pullback", version="1.0.0", profile="swing", timeframe="4H", htf="1D",
                            max_staleness_intervals=1.5, zone_lookback=80, min_rr=2.0, expiry_bars=10),
    "scalp": StrategyConfig(name="smc_trend_pullback", version="1.0.0", profile="scalp", timeframe="15m", htf="1H",
                            max_staleness_intervals=1.5, max_gaps=0, zone_lookback=40, zone_max_dist_atr=1.0,
                            min_rr=1.5, expiry_bars=8, slippage=0.0008),
}
