BORROW_LIMIT = 5
RESERVATION_LIMIT = 5


def is_within_borrow_limit(active_borrow_count: int) -> bool:
    return active_borrow_count < BORROW_LIMIT


def is_within_reservation_limit(reservation_count: int) -> bool:
    return reservation_count < RESERVATION_LIMIT
