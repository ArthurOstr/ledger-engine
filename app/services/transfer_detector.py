from collections import defaultdict
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction

TRANSFER_MCC_CODES: set[int] = {4829, 6536, 6537, 6538}

TRANSFER_KEYWORDS: tuple[str, ...] = (
    "переказ",
    "з картки",
    "на картку",
    "між рахунками",
    "поповнення картки",
    "p2p",
    "card2card",
    "перевод",
    "с карты",
    "на карту",
)

PAIRING_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours


def _has_transfer_signal(tx: Transaction) -> bool:
    """Checks whether a transaction carries P2P/transfer MCC or description cues."""
    if tx.mcc in TRANSFER_MCC_CODES:
        return True

    haystack = f"{tx.description or ''} {tx.category or ''}".lower()
    return any(kw in haystack for kw in TRANSFER_KEYWORDS)


def _account_key(tx: Transaction) -> tuple[str, str]:
    """Identifies the bank + card pair to prevent matching a card against itself."""
    return (
        str(tx.bank or "").strip().lower(),
        str(tx.card or "").strip(),
    )


async def detect_and_mark_transfers(db: AsyncSession, user_id: int) -> int:
    """
    Finds unpaired UAH outflow/inflow pairs across distinct cards owned by `user_id`
    within a 24-hour window and flags both legs with `is_transfer = True`.
    Returns the number of individual transactions marked.
    """
    stmt = (
        select(Transaction)
        .where(
            Transaction.owner_id == user_id,
            Transaction.currency == "UAH",
            Transaction.is_transfer.is_(False),
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
    )
    result = await db.execute(stmt)
    unpaired = list(result.scalars().all())

    if len(unpaired) < 2:
        return 0

    outflows: list[Transaction] = []
    inflows_by_amount: dict[Decimal, list[Transaction]] = defaultdict(list)

    for tx in unpaired:
        if tx.amount < Decimal("0"):
            outflows.append(tx)
        elif tx.amount > Decimal("0"):
            inflows_by_amount[tx.amount].append(tx)

    matched_ids: set[int] = set()
    marked_count = 0

    for out_tx in outflows:
        if out_tx.id in matched_ids:
            continue

        target_amount = abs(out_tx.amount)
        candidates = inflows_by_amount.get(target_amount)
        if not candidates:
            continue

        out_account = _account_key(out_tx)
        best_match: Transaction | None = None
        best_delta: float = float("inf")

        for in_tx in candidates:
            if in_tx.id in matched_ids:
                continue
            if _account_key(in_tx) == out_account:
                continue

            delta_seconds = abs((in_tx.date - out_tx.date).total_seconds())
            if delta_seconds > PAIRING_WINDOW_SECONDS:
                continue

            if not (_has_transfer_signal(out_tx) or _has_transfer_signal(in_tx)):
                continue

            if delta_seconds < best_delta:
                best_delta = delta_seconds
                best_match = in_tx

        if best_match is not None:
            out_tx.is_transfer = True
            best_match.is_transfer = True
            matched_ids.add(out_tx.id)
            matched_ids.add(best_match.id)
            marked_count += 2

    if marked_count > 0:
        await db.commit()

    return marked_count