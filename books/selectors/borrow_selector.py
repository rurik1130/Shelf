from ..models import Borrow


def count_active_borrows(user):
    return Borrow.objects.filter(
        user=user,
        returned_at__isnull=True,
    ).count()


def get_active_borrow(book, user):
    return Borrow.objects.filter(
        book=book,
        user=user,
        returned_at__isnull=True,
    ).first()


def get_active_borrow_by_book(book):
    return Borrow.objects.filter(book=book, returned_at__isnull=True).first()


def get_active_borrows_by_user(user):
    return Borrow.objects.filter(user=user, returned_at__isnull=True).select_related(
        "book"
    )
