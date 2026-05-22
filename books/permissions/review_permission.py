from ..models import Borrow


def can_review(book, user):
    return Borrow.objects.filter(book=book, user=user).exists()


def can_delete_review(*, review, user):
    return review.user_id == user.id
