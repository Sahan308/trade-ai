"""Risk tools: contract specs and position sizing. Calculations only — nothing is ever sent to an exchange."""
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from ..providers.base import MarketType, ProviderError
from ..risk.sizing import size_position
from .markets import SymbolPath, get_provider, provider_error

router = APIRouter(prefix="/api", tags=["risk"])


@router.get("/markets/{symbol}/specs", summary="Tick size, lot size, minimums and maintenance margin")
def specs(request: Request, symbol: SymbolPath, market: MarketType = MarketType.spot, provider=Depends(get_provider)):
    try:
        return provider.specs(market, symbol)
    except ProviderError as exc:
        return provider_error(request, exc)


@router.get("/risk/size", summary="Position size from account risk and stop distance")
def size(request: Request, balance: float = Query(..., gt=0), risk_pct: float = Query(..., gt=0, le=100),
         entry: float = Query(..., gt=0), stop: float = Query(..., gt=0), side: Literal["LONG", "SHORT"] = "LONG",
         market: MarketType = MarketType.spot, leverage: float = Query(1, ge=1, le=125),
         fee_rate: float | None = Query(None, ge=0, le=0.01), slippage: float = Query(0.0005, ge=0, le=0.05),
         hold_hours: float = Query(0, ge=0, le=24 * 90), symbol: str | None = Query(None, pattern=r"^[A-Za-z0-9]{2,15}USDT$"),
         provider=Depends(get_provider)):
    """If `symbol` is given, exchange specs (and funding for Futures) are fetched and applied."""
    sp, funding, notes = None, None, []
    if symbol:
        try:
            sp = provider.specs(market, symbol)
        except ProviderError as exc:
            notes.append(f"Exchange specs unavailable ({exc.message}); no lot/tick rounding applied.")
        if market == MarketType.futures:
            try:
                funding = provider.funding(symbol).funding_rate
            except ProviderError:
                notes.append("Funding rate unavailable; funding cost not estimated.")
    fee = fee_rate if fee_rate is not None else (0.0005 if market == MarketType.futures else 0.001)
    out = size_position(balance, risk_pct, entry, stop, side, market.value, leverage, fee, slippage, sp, funding, hold_hours)
    out["specs"] = sp
    out["notes"] = notes
    return out
