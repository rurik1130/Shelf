from django.db import transaction
from django.utils import timezone

from ..domain.limits import is_within_borrow_limit
from ..models import Borrow, Reservation
from ..selectors.borrow_selector import count_active_borrows


@transaction.atomic
def borrow_book(*, user, book, borrowed_at):
    active_count = count_active_borrows(user)

    if not is_within_borrow_limit(active_count):
        return None, "上限超過"

    borrow = Borrow.objects.create(
        user=user,
        book=book,
        borrowed_at=borrowed_at,
    )

    Reservation.objects.filter(user=user, book=book).delete()

    return borrow, None


@transaction.atomic
def return_book(*, borrow, user):

    if borrow.user_id != user.id:
        return None, "権限がありません"

    if borrow.returned_at is not None:
        return None, "既に返却済みです"

    borrow.returned_at = timezone.now()
    borrow.save(update_fields=["returned_at"])

    return borrow, None
