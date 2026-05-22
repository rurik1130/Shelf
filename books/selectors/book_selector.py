from django.db.models import Avg, Prefetch
from django.shortcuts import get_object_or_404

from ..models import Book, Borrow


def get_books_for_list():
    return Book.objects.filter(deleted_at__isnull=True).prefetch_related(
        Prefetch(
            "borrow_set",
            queryset=Borrow.objects.filter(returned_at__isnull=True),
            to_attr="prefetched_active_borrows",
        ),
        Prefetch(
            "reservation_set",
            to_attr="book_reservations",
        ),
    )


def get_book_list_with_user_status(books, user):
    book_list = []
    for book in books:
        status_info = book.get_status_display()
        label = status_info["label"]
        color = status_info["color"]

        is_my_borrow = False
        is_my_reserve = False
        can_borrow_now = False
        due_date_message = None

        active_borrow = book.get_active_borrow()
        is_borrowed = active_borrow is not None

        first_res = book.get_first_reservation()
        has_reservation = first_res is not None

        # 自分が「今借りている張本人」である場合の表示切り替え
        if is_borrowed and user.is_authenticated and active_borrow.user == user:
            is_my_borrow = True
            label = "貸出中"
            color = "mine"
            remaining = active_borrow.get_remaining_days()
            # 返却期限が迫っている場合のメッセージ生成
            if remaining is not None and remaining <= 7:
                due_date_message = f"期限まであと{remaining}日"

        # 自分が「最初の予約者」である場合、まだ誰も借りていなければ今すぐ借りられる権限を与える
        elif has_reservation and user.is_authenticated and first_res.user == user:
            is_my_reserve = True
            label = "予約中"
            color = "mine"
            if not is_borrowed:
                can_borrow_now = True

        # 自分に関係のない本の場合「誰も借りておらず、予約も入っていない」状態の時だけ、トップ画面から直で即時貸出ができる
        else:
            if not is_borrowed and not has_reservation:
                can_borrow_now = True

            label = status_info["label"]
            color = status_info["color"]

        book_list.append(
            {
                "book": book,
                "label": label,
                "color": color,
                "status": status_info.get("status"),
                "is_my_borrow": is_my_borrow,
                "is_my_reserve": is_my_reserve,
                "can_borrow_now": can_borrow_now,
                "due_date_message": due_date_message,
            }
        )
    return book_list


def get_book_detail(book_id):
    return get_object_or_404(
        Book.objects.prefetch_related(
            Prefetch(
                "borrow_set",
                queryset=Borrow.objects.filter(returned_at__isnull=True),
                to_attr="active_borrows",
            ),
            Prefetch(
                "reservation_set",
                to_attr="book_reservations",
            ),
        ).annotate(avg_rating=Avg("review__rating")),
        id=book_id,
        deleted_at__isnull=True,
    )


def get_active_book_by_id(book_id):
    return get_object_or_404(
        Book.objects.filter(deleted_at__isnull=True),
        id=book_id,
    )
