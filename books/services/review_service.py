from django.db import transaction


@transaction.atomic
def save_review(*, book, user, form):

    review = form.save(commit=False)
    review.book = book
    review.user = user
    review.save()

    return review


@transaction.atomic
def delete_review(*, review, user):

    if review.user_id != user.id:
        return False, "権限がありません"

    review.delete()

    return True, None
