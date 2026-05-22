from .borrow_selector import get_active_borrows_by_user
from .reservation_selector import get_user_reservations
from .review_selector import get_user_review_map_by_book


def get_mypage_data(user):
    borrows = get_active_borrows_by_user(user)
    reservations = get_user_reservations(user)
    reviews_by_book_id = get_user_review_map_by_book(user)

    return borrows, reservations, reviews_by_book_id
