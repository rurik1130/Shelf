from django.utils import timezone


def delete_book(book):
    book.deleted_at = timezone.now()
    book.save(update_fields=["deleted_at"])


def get_book_status(book):
    """本の現在のステータスを動的に判定する"""

    # 一覧ページなどでのn+1問題を防ぐため、
    # Selector層で prefetch_related されたキャッシュデータ（prefetched_active_borrows）が存在する場合は、それを使用する
    # キャッシュがない（詳細画面など単一取得の）場合は、通常通りDBへクエリを発行する
    borrows = getattr(book, "prefetched_active_borrows", None)
    if borrows is not None:
        if borrows:
            return "borrowed"
    else:
        if book.borrow_set.filter(returned_at__isnull=True).exists():
            return "borrowed"

    # 上記と同様に、予約データのn+1問題対策のキャッシュを優先してチェックする
    reservations = getattr(book, "book_reservations", None)
    if reservations is not None:
        if reservations:
            return "reserved"
    else:
        if book.reservation_set.exists():
            return "reserved"

    return "available"
