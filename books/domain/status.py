STATUS_MAP = {
    "available": ("貸出可", "green"),
    "reserved": ("予約可", "orange"),
    "borrowed": ("貸出中", "red"),
    "waiting": ("予約者待ち", "gray"),
}


def filter_books_by_status(books, status_filter):
    if not status_filter:
        return books

    return [book for book in books if book.get_status() == status_filter]


def resolve_status_display(book):
    # n+1問題対策：prefetchされたデータがあればそれを使い、なければ愚直にDBに問い合わせる
    active_borrows = getattr(book, "prefetched_active_borrows", None)
    if active_borrows is None:
        active_borrows = book.borrow_set.filter(returned_at__isnull=True)

    reservations = getattr(book, "book_reservations", None)
    if reservations is None:
        reservations = book.reservation_set.all()

    has_borrow = (
        len(active_borrows) > 0
        if isinstance(active_borrows, list)
        else active_borrows.exists()
    )
    has_reservation = (
        len(reservations) > 0
        if isinstance(reservations, list)
        else reservations.exists()
    )

    # ステータスマトリクスの判定
    if has_borrow:
        # 誰かが借りていて、かつ次の予約者も並んでいる状態
        if has_reservation:
            return {
                "status": "borrowed",
                "label": "貸出中",
                "color": "danger",
            }
        # 誰かが借りているが、次の予約はまだ入っていない状態（＝予約が可能）
        else:
            return {
                "status": "reserved",
                "label": "予約可",
                "color": "warning",
            }

    else:
        # 本は返却されて棚にあるが、予約者がいるため「その予約者専用のキープ」状態
        if has_reservation:
            return {
                "status": "waiting",
                "label": "予約者待ち",
                "color": "secondary",
            }
        # 誰も借りておらず、予約もない状態（＝誰でも今すぐ借りられる）
        else:
            return {
                "status": "available",
                "label": "貸出可",
                "color": "success",
            }
