"""Who may see a signal's trade levels (Milestone 7 server-side trial).

Levels of a *live* LONG/SHORT signal (lifecycle active or triggered) are hidden unless the viewer has unlocked
it (one trial signal each) or has a paid plan. Finished signals are shown in full, so past outcomes stay transparent."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Signal, SignalUnlock, User
from .signals.store import to_api

LIVE = ("active", "triggered")
LOCKED_FIELDS = ("entry_low", "entry_high", "stop", "targets", "target_sources", "rr", "rr_net", "invalidation", "position", "outcome")
LOCKED_MESSAGE = "Trade levels are hidden. Sign in and unlock this signal to see entry, stop and targets."


def unlocked_ids(session: Session, user: User | None) -> set[str] | None:
    """None = everything visible (paid plan); otherwise the ids this viewer has unlocked."""
    if user is not None and user.plan != "trial":
        return None
    if user is None:
        return set()
    return set(session.scalars(select(SignalUnlock.signal_id).where(SignalUnlock.user_id == user.id)))


def is_locked(row: Signal, unlocked: set[str] | None) -> bool:
    return (row.side in ("LONG", "SHORT") and row.lifecycle in LIVE and unlocked is not None and row.id not in unlocked)


def view(row: Signal, unlocked: set[str] | None) -> dict:
    d = to_api(row)
    locked = is_locked(row, unlocked)
    if locked:
        for k in LOCKED_FIELDS:
            d.pop(k, None)
    d["locked"] = locked
    return d
