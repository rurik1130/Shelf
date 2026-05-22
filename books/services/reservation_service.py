from django.db import transaction

from ..domain.limits import is_within_reservation_limit
from ..models import Reservation
from ..permissions.borrow_permission import can_reserve
from ..selectors.reservation_selector import (
    count_reservations_by_user,
    get_first_reservation,
)
from ..selectors.borrow_selector import get_active_borrow_by_book


@transaction.atomic
def reserve_book(*, user, book):
    reservation_count = count_reservations_by_user(user)

    if not is_within_reservation_limit(reservation_count):
        return None, "予約上限に達しています"

    current_borrow = get_active_borrow_by_book(book)
    existing_reservation = get_first_reservation(book)

    if not can_reserve(
        has_current_borrow=(current_borrow is not None),
        has_reservation=(existing_reservation is not None),
    ):
        return None, "この本は予約できません"

    reservation = Reservation.objects.create(
        user=user,
        book=book,
    )

    return reservation, None


@transaction.atomic
def cancel_reservation(*, user, book):
    reservation = Reservation.objects.filter(
        user=user,
        book=book,
    ).first()

    if not reservation:
        return False, "予約が存在しません"

    reservation.delete()

    return True, None


@transaction.atomic
def fulfill_reservation(*, reservation, user):
    if reservation.user_id != user.id:
        return False, "権限がありません"

    reservation.delete()

    return True, None
