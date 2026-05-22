from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Location(models.Model):
    """書籍の保管場所を管理する"""

    name = models.CharField(max_length=100, verbose_name="保管場所名")

    def __str__(self):
        return self.name


class Book(models.Model):
    """本（蔵書）の情報を管理するモデル 貸出状況や予約状況に基づいた動的なステータス判定機能を持つ"""

    # フロントエンド（HTML/CSS）のバッジ表示にそのまま連動できるよう、判定用のステータスキーに対して、文言と色（CSSクラス名）をマッピング
    STATUS_LABELS = {
        "available": {"label": "貸出可", "color": "success"},
        "reserved": {
            "label": "予約可",
            "color": "warning",
        },
        "borrowed": {
            "label": "貸出中",
            "color": "danger",
        },
        "waiting": {
            "label": "予約者待ち",
            "color": "secondary",
        },
    }

    isbn = models.CharField(max_length=20, blank=True, null=True)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    cover_image_url = models.TextField(blank=True, null=True)
    publication_date = models.DateField(blank=True, null=True)
    purchase_date = models.DateField(blank=True, null=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="保管場所",
    )
    deleted_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.title} ({self.author})"

    def get_first_reservation(self):
        """現在入っている最初の予約を取得する prefetch_related時はキャッシュを利用"""
        if hasattr(self, "book_reservations"):
            return self.book_reservations[0] if self.book_reservations else None
        return self.reservation_set.first()

    def get_active_borrow(self):
        """現在貸出中のレコードを1件取得する"""
        if hasattr(self, "active_borrows"):
            return self.active_borrows[0] if self.active_borrows else None
        return self.borrow_set.filter(returned_at__isnull=True).first()

    def has_active_borrow(self):
        """現在誰かに貸し出されているかどうかを判定"""
        if hasattr(self, "active_borrows"):
            return bool(self.active_borrows)
        return self.borrow_set.filter(returned_at__isnull=True).exists()

    def has_reservation(self):
        """現在予約が入っているかどうかを判定"""
        if hasattr(self, "book_reservations"):
            return bool(self.book_reservations)
        return self.reservation_set.exists()

    def get_status(self):
        """本の内容・貸出状況・予約状況から現在のステータスコードを返す"""
        has_borrow = self.has_active_borrow()
        has_reservation = self.has_reservation()

        if has_borrow:
            if has_reservation:
                return "borrowed"
            return "reserved"

        if has_reservation:
            return "waiting"

        return "available"

    def get_status_display(self):
        """テンプレート表示用のステータス情報（ラベルや色）を一括で返す"""
        status = self.get_status()
        return {
            "status": status,
            **self.STATUS_LABELS[status],
        }


class Borrow(models.Model):
    """貸出履歴および現在の貸出状況を管理する"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    book = models.ForeignKey("Book", on_delete=models.CASCADE)
    borrowed_at = models.DateField()
    returned_at = models.DateTimeField(blank=True, null=True)

    BORROW_PERIOD_DAYS = 365

    def _today(self):
        """判定用の当日日付を取得"""
        return timezone.now().date()

    def get_due_date(self):
        """返却期限日を計算する"""
        return self.borrowed_at + timedelta(days=self.BORROW_PERIOD_DAYS)

    def _date_diff(self):
        """期限日と現在日の差分日数を計算"""
        return (self.get_due_date() - self._today()).days

    def is_overdue(self):
        """返却期限を過ぎているか判定 返却済みの場合はFalseを返す"""
        if self.returned_at:
            return False
        return self._date_diff() < 0

    def get_remaining_days(self):
        """返却期限までの残り日数を返す 期限切れの場合はNone"""
        if self.returned_at:
            return None
        diff = self._date_diff()
        return diff if diff >= 0 else None

    def get_overdue_days(self):
        """期限を過ぎている日数を返す 期限内の場合はNone"""
        if self.returned_at:
            return None
        diff = self._date_diff()
        return -diff if diff < 0 else None


class Reservation(models.Model):
    """本の予約状況を管理する"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    book = models.ForeignKey("Book", on_delete=models.CASCADE)
    reserved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 1冊の本に対して、同時に存在できる予約は1つまで
        constraints = [
            models.UniqueConstraint(
                fields=["book"],
                name="unique_reservation_per_book",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.book}"


class Review(models.Model):
    """本に対するユーザーの評価とコメント"""

    RATING_CHOICES = [
        (1, "★1"),
        (2, "★2"),
        (3, "★3"),
        (4, "★4"),
        (5, "★5"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["book", "user"],
                name="unique_review_per_user_book",
            )
        ]

    def __str__(self):
        return f"{self.book.title} - {self.user}"
