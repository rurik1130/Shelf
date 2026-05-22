def build_mypage_view_model(borrows, reservations, reviews_by_book_id):
    borrow_list = []
    my_borrowed_book_ids = {borrow.book_id for borrow in borrows}

    reservation_map = {r.book_id: r for r in reservations}
    reservation_list = []

    for borrow in borrows:
        book = borrow.book
        borrow_list.append(
            {
                "book": book,
                "location": book.location,
                "borrowed_at": borrow.borrowed_at,
                "due_date": borrow.get_due_date(),
                "is_overdue": borrow.is_overdue(),
                "remaining_days": borrow.get_remaining_days(),
                "overdue_days": borrow.get_overdue_days(),
                "has_reservation": book.id in reservation_map,
                "my_review": reviews_by_book_id.get(book.id),
            }
        )

    for reservation in reservations:
        book = reservation.book

        if book.id in my_borrowed_book_ids:
            continue

        is_borrowed = book.has_active_borrow()

        can_borrow = not is_borrowed

        reservation_list.append(
            {
                "book": book,
                "location": book.location,
                "reserved_at": reservation.reserved_at,
                "can_borrow": can_borrow,
            }
        )

    return borrow_list, reservation_list
