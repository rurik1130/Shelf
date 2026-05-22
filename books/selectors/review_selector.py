from django.shortcuts import get_object_or_404
from ..models import Review


def get_user_reviews_with_books(user):
    return (
        Review.objects.filter(user=user).select_related("book").order_by("-created_at")
    )


def get_user_review_map_by_book(user):
    return {
        r.book_id: r for r in Review.objects.filter(user=user).select_related("book")
    }


def get_user_review(*, book, user):
    return Review.objects.filter(book=book, user=user).first()


def get_review_by_id(review_id):
    return get_object_or_404(Review, id=review_id)
