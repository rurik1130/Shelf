from ..models import Reservation


def count_reservations_by_user(user):
    return Reservation.objects.filter(user=user).count()


def get_first_reservation(book):
    return Reservation.objects.filter(book=book).order_by("reserved_at").first()


def get_user_reservations(user):
    return Reservation.objects.filter(user=user).select_related("book")
