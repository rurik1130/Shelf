from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .domain.status import filter_books_by_status
from .external.google_books_client import fetch_cover_by_isbn
from .forms import BookForm, ReviewForm
from .integrations.openbd import fetch_openbd
from .models import Book, Borrow, Location, Reservation, Review
from .selectors.book_selector import (
    get_book_list_with_user_status,
    get_books_for_list,
)
from .services import book_import_service, book_service
from .services.book_import_service import (
    _resolve_cover,
)
from .utils import date, text


class BookTestBase(TestCase):
    """共通のセットアップロジックを管理するベースクラス"""

    def setUp(self):
        self.password = "test12345"
        self.location = Location.objects.create(name="共通棚")
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=self.password
        )

    def login_user(self, user=None):
        """指定したユーザーでログインするヘルパー"""
        target_user = user or self.user
        self.client.login(username=target_user.username, password=self.password)


class BookViewTest(BookTestBase):
    """本の一覧・詳細表示の検証"""

    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            title="テスト駆動開発",
            author="Kent Beck",
            isbn="9784274217883",
            location=self.location,
        )
        self.list_url = reverse("books:book_list")
        self.detail_url = reverse("books:book_detail", args=[self.book.id])

    def test_book_list_page_for_logged_in_user(self):
        """ログインユーザーは一覧ページにアクセスでき、本が表示されるか"""

        self.login_user()

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/book_list.html")
        self.assertContains(response, self.book.title)

    def test_book_list_page_redirect_for_anonymous_user(self):
        """未ログインユーザーはログイン画面へリダイレクトされるか"""

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 302)

    def test_book_detail_page(self):
        """本の詳細ページが正しく表示されるか"""

        self.login_user()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/book_detail.html")
        self.assertContains(response, self.book.author)

    def test_book_detail_404(self):
        """存在しない本にアクセスした際に404エラーを返すか"""

        self.login_user()

        response = self.client.get(reverse("books:book_detail", args=[99999]))

        self.assertEqual(response.status_code, 404)


class BookSearchTest(BookTestBase):
    """検索機能のフィルタリング検証"""

    def setUp(self):
        super().setUp()
        self.list_url = reverse("books:book_list")

        self.book_py = Book.objects.create(
            title="Python入門編", author="春野翡翠", location=self.location
        )
        self.book_dj = Book.objects.create(
            title="Django応用編", author="夏目琥珀", location=self.location
        )
        self.book_novel = Book.objects.create(
            title="小説A", author="春野瑠璃", location=self.location
        )

    def test_search_by_title(self):
        """タイトルによる部分一致検索が正しく機能するか"""

        self.login_user()
        query = "Python"

        response = self.client.get(self.list_url, {"q": query})

        self.assertContains(response, self.book_py.title)
        self.assertNotContains(response, self.book_dj.title)

    def test_search_by_author(self):
        """著者名による部分一致検索で、複数の該当者がヒットするか"""

        self.login_user()
        query = "春野"

        response = self.client.get(self.list_url, {"q": query})

        self.assertContains(response, self.book_py.title)
        self.assertContains(response, self.book_novel.title)
        self.assertNotContains(response, self.book_dj.title)

    def test_search_no_result(self):
        """該当する本がない場合に、リストが空になるか"""

        self.login_user()
        query = "存在しない本"

        response = self.client.get(self.list_url, {"q": query})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.book_py.title)
        self.assertNotContains(response, self.book_dj.title)
        self.assertNotContains(response, self.book_novel.title)


class MyPageTest(BookTestBase):
    """マイページにおける個人データの表示検証"""

    def setUp(self):
        super().setUp()
        self.mypage_url = reverse("books:mypage")

        self.my_borrowed_book = Book.objects.create(
            title="借りている本", location=self.location
        )
        Borrow.objects.create(
            user=self.user, book=self.my_borrowed_book, borrowed_at=timezone.now()
        )

        self.my_reserved_book = Book.objects.create(
            title="予約した本", location=self.location
        )
        Reservation.objects.create(user=self.user, book=self.my_reserved_book)

    def test_mypage_display_own_content(self):
        """自分の貸出中および予約中の本が正しく表示されるか"""

        self.login_user()

        response = self.client.get(self.mypage_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/mypage.html")
        self.assertContains(response, self.my_borrowed_book.title)
        self.assertContains(response, self.my_reserved_book.title)

    def test_mypage_should_not_display_others_content(self):
        """他人の貸出データがマイページに混入していないか"""

        self.login_user()
        other_user = User.objects.create_user(username="other", password="password")
        other_book = Book.objects.create(title="他人の本", location=self.location)
        Borrow.objects.create(
            user=other_user, book=other_book, borrowed_at=timezone.now()
        )

        response = self.client.get(self.mypage_url)

        self.assertContains(response, self.my_borrowed_book.title)
        self.assertNotContains(response, other_book.title)


class BookOperationTest(BookTestBase):
    """貸出・予約・返却ロジックの検証"""

    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            title="Django実践ガイド", author="テスト著者", location=self.location
        )

    def test_borrow_book_success(self):
        """本を正常に借りられるか"""

        self.login_user()
        borrow_url = reverse("books:borrow_book", args=[self.book.id])
        data = {"borrowed_at": timezone.now().date()}

        response = self.client.post(borrow_url, data=data, follow=True)

        self.assertEqual(response.status_code, 200)
        is_borrowed = Borrow.objects.filter(
            user=self.user, book=self.book, returned_at__isnull=True
        ).exists()
        self.assertTrue(is_borrowed)

        self.book.refresh_from_db()
        self.assertEqual(self.book.get_status(), "reserved")

    def test_reserve_book_success(self):
        """貸出中の本を正常に予約できるか"""

        other_user = User.objects.create_user(username="other", password="password")
        Borrow.objects.create(
            user=other_user, book=self.book, borrowed_at=timezone.now()
        )

        self.login_user()
        reserve_url = reverse("books:reserve_book", args=[self.book.id])

        response = self.client.post(reserve_url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Reservation.objects.filter(user=self.user, book=self.book).exists()
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.get_status(), "borrowed")

    def test_return_book_success(self):
        """本を正常に返却できるか"""

        self.login_user()
        borrow = Borrow.objects.create(
            user=self.user, book=self.book, borrowed_at=timezone.now()
        )
        return_url = reverse("books:return_book", args=[self.book.id])

        response = self.client.post(return_url, follow=True)

        self.assertEqual(response.status_code, 200)
        borrow.refresh_from_db()
        self.assertIsNotNone(borrow.returned_at)

        self.book.refresh_from_db()
        self.assertEqual(self.book.get_status(), "available")


class BookActionFlowTest(BookTestBase):
    """予約キャンセル・レビュー削除等の詳細フロー検証"""

    def test_cancel_reservation_success(self):
        """予約のキャンセルが正常に処理され、完了画面が表示されるか"""
        self.login_user()
        book = Book.objects.create(title="予約キャンセル本", location=self.location)
        Reservation.objects.create(user=self.user, book=book)
        url = reverse("books:cancel_reservation", args=[book.id])

        response = self.client.post(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/reserve_cancel_complete.html")
        self.assertFalse(Reservation.objects.filter(user=self.user, book=book).exists())


class BookStatusLogicTest(BookTestBase):
    """status.py の判定ロジックおよびフィルタリングの検証"""

    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            title="ステータス検証本", location=self.location
        )

    def test_filter_books_by_status(self):
        """ステータスフィルタリングが正しく機能するか"""
        Borrow.objects.create(
            user=self.user, book=self.book, borrowed_at=timezone.now()
        )

        book_available = Book.objects.create(title="貸出可本", location=self.location)

        books = [self.book, book_available]

        self.assertEqual(len(filter_books_by_status(books, None)), 2)

        filtered = filter_books_by_status(books, "reserved")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].title, "ステータス検証本")

    def test_resolve_status_display_borrowed_and_reserved(self):
        """貸出中で、かつ予約も入っている場合のステータス判定"""
        Borrow.objects.create(
            user=self.user, book=self.book, borrowed_at=timezone.now()
        )
        other_user = User.objects.create_user(
            username="other_status", password=self.password
        )
        Reservation.objects.create(user=other_user, book=self.book)

        status_info = self.book.get_status_display()

        self.assertEqual(status_info["status"], "borrowed")
        self.assertEqual(status_info["label"], "貸出中")

    def test_resolve_status_display_waiting_for_reservation(self):
        """貸出はされていないが、予約が入っている（予約者待ち）場合のステータス判定"""

        Reservation.objects.create(user=self.user, book=self.book)

        status_info = self.book.get_status_display()

        self.assertEqual(status_info["status"], "waiting")
        self.assertEqual(status_info["label"], "予約者待ち")

    def test_resolve_status_display_reserved_only(self):
        """貸出中だが、予約は空いている（次に予約できる）場合のステータス判定"""

        Borrow.objects.create(
            user=self.user, book=self.book, borrowed_at=timezone.now()
        )

        status_info = self.book.get_status_display()

        self.assertEqual(status_info["status"], "reserved")
        self.assertEqual(status_info["label"], "予約可")


class BookServiceTest(BookTestBase):
    """book_service.py のビジネスロジック検証"""

    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            title="サービス本", author="著者", location=self.location
        )

    def test_get_book_status_prefetch_logic(self):
        """prefetchされた属性がある場合、DBクエリなしでステータス判定されるか"""
        self.book.prefetched_active_borrows = [True]
        self.assertEqual(book_service.get_book_status(self.book), "borrowed")

        self.book.prefetched_active_borrows = []
        self.book.book_reservations = [True]
        self.assertEqual(book_service.get_book_status(self.book), "reserved")

    def test_get_book_status_db_query_fallback(self):
        """prefetch属性がない場合、通常のDBクエリルートで判定されるか"""
        other_user = User.objects.create_user(username="u1", password=self.password)
        Borrow.objects.create(
            user=other_user, book=self.book, borrowed_at=timezone.now()
        )

        self.assertEqual(book_service.get_book_status(self.book), "borrowed")

    def test_book_list_status_due_soon(self):
        """期限まで7日以内の貸出がある場合、メッセージが表示されるか"""

        self.login_user()

        Borrow.objects.create(
            user=self.user, book=self.book, borrowed_at=timezone.now(), returned_at=None
        )

        with patch("books.models.Borrow.get_remaining_days") as mock_remaining:
            mock_remaining.return_value = 3

            books = get_books_for_list()
            book_list = get_book_list_with_user_status(books, self.user)

            target = next(item for item in book_list if item["book"].id == self.book.id)

            self.assertEqual(target["due_date_message"], "期限まであと3日")
            self.assertTrue(target["is_my_borrow"])

    def test_book_list_status_reserved_and_available(self):
        """自分が予約しており、かつ本が棚にある（貸出可能）な状態の判定"""

        self.login_user()
        Reservation.objects.create(user=self.user, book=self.book)

        books = get_books_for_list()
        book_list = get_book_list_with_user_status(books, self.user)

        target = next(item for item in book_list if item["book"].id == self.book.id)
        self.assertTrue(target["is_my_reserve"])
        self.assertTrue(target["can_borrow_now"])


class BookReviewTest(BookTestBase):
    """レビュー機能（投稿権限と保存）の検証"""

    def setUp(self):
        super().setUp()
        self.book = Book.objects.create(
            title="レビュー対象本", author="著者", location=self.location
        )
        self.review_url = reverse("books:add_review", args=[self.book.id])

    def test_add_review_permission_fail(self):
        """一度も借りたことがない本にはレビューを書けず、リダイレクトされるか"""

        self.login_user()

        response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 302)

    def test_add_review_success(self):
        """返却済みの貸出履歴があれば、レビューを投稿できるか"""

        self.login_user()
        Borrow.objects.create(
            user=self.user,
            book=self.book,
            borrowed_at=timezone.now(),
            returned_at=timezone.now(),
        )
        review_data = {"rating": 5, "comment": "オススメ"}

        get_response = self.client.get(self.review_url)
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(self.review_url, data=review_data, follow=True)

        self.assertEqual(post_response.status_code, 200)
        self.assertTrue(
            Review.objects.filter(
                user=self.user, book=self.book, rating=5, comment="オススメ"
            ).exists()
        )

    def test_delete_review_flow(self):
        """レビュー削除の確認画面表示と、削除実行後のリダイレクト検証"""
        self.login_user()
        book = Book.objects.create(title="レビュー削除本", location=self.location)
        review = Review.objects.create(
            user=self.user, book=book, rating=3, comment="削除本"
        )

        confirm_url = reverse("books:delete_review", args=[review.id])

        response_get = self.client.get(confirm_url)
        self.assertEqual(response_get.status_code, 200)

        response_post = self.client.post(confirm_url, follow=True)

        self.assertRedirects(response_post, reverse("books:review_delete_complete"))
        self.assertFalse(Review.objects.filter(id=review.id).exists())


class ReviewFormValidationTest(TestCase):
    """ReviewFormのカスタムバリデーションと整形処理の検証"""

    def test_review_form_valid_data(self):
        """正しいデータであればバリデーションを通過するか"""

        form_data = {"rating": 5, "comment": "  オススメ  "}

        form = ReviewForm(data=form_data)

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["comment"], "オススメ")

    def test_review_form_missing_rating(self):
        """レーティングが空の場合にエラーが発生するか"""

        form_data = {"rating": None, "comment": "テストコメント"}

        form = ReviewForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn("rating", form.errors)
        self.assertIn("このフィールドは必須です。", form.errors["rating"][0])

    def test_review_form_missing_comment(self):
        """コメントが空の場合にエラーが発生するか"""

        form_data = {"rating": 3, "comment": ""}

        form = ReviewForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn("comment", form.errors)
        self.assertIn("このフィールドは必須です。", form.errors["comment"][0])

    def test_review_form_comment_too_short(self):
        """コメントが2文字未満（1文字）の場合にバリデーションエラーになるか"""

        form_data = {"rating": 4, "comment": "あ"}

        form = ReviewForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn("comment", form.errors)
        self.assertIn("コメントは2文字以上入力してください", form.errors["comment"][0])


class BookStaffTest(BookTestBase):
    """スタッフ専用機能（登録・編集・削除）の検証"""

    def setUp(self):
        super().setUp()
        self.staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password=self.password,
            is_staff=True,
        )

        self.book = Book.objects.create(
            title="編集前のタイトル", author="著者", location=self.location
        )

    def test_book_create_by_staff_success(self):
        """スタッフ権限があれば本を新規登録できるか"""

        self.login_user(self.staff_user)
        url = reverse("books:book_create")
        create_data = {
            "title": "新規登録の本",
            "author": "新規著者",
            "isbn": "1234567890",
            "location": self.location.id,
        }

        response = self.client.post(url, data=create_data, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Book.objects.filter(title="新規登録の本").exists())

    def test_book_create_by_regular_user_fail(self):
        """一般ユーザーは本を登録できず、リダイレクトされるか"""

        self.login_user(self.user)
        url = reverse("books:book_create")

        response = self.client.post(url, data={"title": "ダメな本"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Book.objects.filter(title="ダメな本").exists())

    def test_book_update_by_staff(self):
        """スタッフが本の情報を編集し、DBが更新されるか"""

        self.login_user(self.staff_user)
        url = reverse("books:book_update", args=[self.book.id])
        update_data = {
            "title": "編集後のタイトル",
            "author": "著者",
            "location": self.location.id,
        }

        response = self.client.post(url, data=update_data, follow=True)

        self.assertEqual(response.status_code, 200)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "編集後のタイトル")

    def test_book_delete_by_staff(self):
        """スタッフによる削除が「論理削除」として正しく機能するか"""

        self.login_user(self.staff_user)
        url = reverse("books:book_delete", args=[self.book.id])

        response = self.client.post(url, follow=True)

        self.book.refresh_from_db()
        self.assertIsNotNone(self.book.deleted_at)
        self.assertEqual(response.status_code, 200)

    def test_delete_book_logic(self):
        """delete_book 関数によって論理削除（deleted_at の更新）が行われるか"""

        book_service.delete_book(self.book)

        self.assertIsNotNone(self.book.deleted_at)

    def test_book_create_invalid(self):
        """不正なデータ（タイトル空）での投稿時にバリデーションエラーが発生するか"""

        self.login_user(self.staff_user)
        url = reverse("books:book_create")
        invalid_data = {"title": "", "author": "著者", "location": self.location.id}

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(url, data=invalid_data)

        self.assertEqual(response.status_code, 200)

        form = response.context["form"]
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

        self.assertIn("このフィールドは必須です。", form.errors["title"])

    def test_book_delete_404(self):
        """存在しない本の削除を試みた際に404エラーを返すか"""

        self.login_user(self.staff_user)

        response = self.client.post(reverse("books:book_delete", args=[99999]))

        self.assertEqual(response.status_code, 404)


class BookStaffAjaxTest(BookTestBase):
    """スタッフ専用Ajax機能の検証"""

    def setUp(self):
        super().setUp()
        self.staff_user = User.objects.create_user(
            username="staff_ajax", password=self.password, is_staff=True
        )

    def test_location_create_ajax_success(self):
        """Ajax経由で新しい保管場所が正常に登録され、JSONが返るか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_create")
        data = {"name": "新設Ajax棚"}

        response = self.client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "新設Ajax棚")
        self.assertTrue(Location.objects.filter(name="新設Ajax棚").exists())


class BookFormSortTest(TestCase):
    """BookFormにおける保管場所(Location)のソートロジックの検証"""

    def setUp(self):
        self.loc_1 = Location.objects.create(name="1F メイン棚")
        self.loc_2 = Location.objects.create(name="2F 専門書棚")
        self.loc_b1 = Location.objects.create(name="B1F 倉庫A")
        self.loc_b2 = Location.objects.create(name="B2F 書庫B")

    def test_location_queryset_sorting_logic(self):
        """Bから始まる棚の特殊ソートおよび降順ソートが正しく適用されているか"""
        form = BookForm()

        sorted_locations = list(form.fields["location"].queryset)

        self.assertTrue(len(sorted_locations) >= 4)

        self.assertEqual(form.fields["location"].empty_label, "場所を選択してください")
        self.assertTrue(form.fields["location"].required)


class LocationViewTest(BookTestBase):
    """保管場所(Location)に関する各ビューの動作・権限・画面遷移の検証"""

    def setUp(self):
        super().setUp()
        self.staff_user = User.objects.create_user(
            username="staffuser",
            email="staff@example.com",
            password=self.password,
            is_staff=True,
        )
        self.test_location = Location.objects.create(name="3F 会議室")

        self.test_book = Book.objects.create(
            title="テスト用の本", author="テスト著者", location=self.test_location
        )

    def test_location_list_accessible_by_staff_only(self):
        """一般ユーザーは拒否され、スタッフユーザーだけが一覧にアクセスできるか"""
        url = reverse("books:location_list")

        self.login_user(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        self.login_user(self.staff_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.test_location, response.context["locations"])

    def test_location_create_combines_floor_and_name(self):
        """作成時に階数と名前が正しく合成されて登録されるか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_create")
        post_data = {"floor": "5", "name": "ミーティングルーム"}

        response = self.client.post(url, data=post_data, follow=True)

        self.assertTrue(Location.objects.filter(name="5F ミーティングルーム").exists())
        self.assertRedirects(response, reverse("books:location_list"))

    def test_location_create_ajax_response(self):
        """Ajaxリクエストによる作成時、正しいJSONが返ってくるか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_create")
        post_data = {"floor": "B1", "name": "集中スペース"}

        response = self.client.post(
            url, data=post_data, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data["name"], "B1F 集中スペース")
        self.assertIn("id", res_data)

    def test_location_create_missing_fields_redirects(self):
        """作成時にフィールドが空の場合、エラーメッセージを表示してリダイレクトされるか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_create")
        post_data = {"floor": "", "name": ""}

        response = self.client.post(url, data=post_data, follow=True)

        self.assertRedirects(response, reverse("books:location_list"))
        messages = [str(m) for m in response.context["messages"]]
        self.assertIn("場所名を入力してください", messages)

    def test_location_update_parses_existing_name_to_form(self):
        """編集画面を開いた際、既存の名前が階数と部屋名に正しく分解されてテンプレートに渡るか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_update", kwargs={"id": self.test_location.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["floor"], "3")
        self.assertEqual(response.context["clean_name"], "会議室")

    def test_location_update_success(self):
        """編集画面からPOSTした際、保管場所の名前が正しく合成されて更新されるか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_update", kwargs={"id": self.test_location.id})
        post_data = {"floor": "7", "name": "展望ラウンジ"}

        response = self.client.post(url, data=post_data, follow=True)

        self.test_location.refresh_from_db()
        self.assertEqual(self.test_location.name, "7F 展望ラウンジ")
        messages = [str(m) for m in response.context["messages"]]
        self.assertIn("保管場所「7F 展望ラウンジ」を更新しました", messages)

    def test_location_delete_success(self):
        """本が紐づいていない場合、保管場所を削除して一覧へリダイレクトされるか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_delete", kwargs={"id": self.test_location.id})

        self.test_book.delete()

        response = self.client.post(url, follow=True)

        self.assertFalse(Location.objects.filter(id=self.test_location.id).exists())
        messages = [str(m) for m in response.context["messages"]]
        self.assertIn(f"保管場所「{self.test_location.name}」を削除しました", messages)

    def test_location_delete_fails_when_books_exist(self):
        """本が紐づいている場合、保管場所の削除がブロックされてエラーメッセージを返すか"""
        self.login_user(self.staff_user)
        url = reverse("books:location_delete", kwargs={"id": self.test_location.id})

        response = self.client.post(url, follow=True)

        self.assertTrue(Location.objects.filter(id=self.test_location.id).exists())
        messages = [str(m) for m in response.context["messages"]]
        self.assertIn(
            "この保管場所には本が登録されているため、削除できません", messages
        )


class ExternalAPITest(TestCase):
    """外部API連携（Google Books / openBD）の検証"""

    @patch("books.external.google_books_client.requests.get")
    def test_fetch_cover_by_isbn_success(self, mock_get):
        """Google Books APIから画像URLを正しく取得できるか"""

        # 実際の外部APIへリクエストが飛ばないよう、期待される正常なJSONレスポンスの構造を擬似的に作成（モック化）
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "volumeInfo": {
                        "imageLinks": {"thumbnail": "http://example.com/cover.jpg"}
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_cover_by_isbn("9784274217883")

        self.assertEqual(result, "https://example.com/cover.jpg")
        mock_get.assert_called_once()

    @patch("books.external.google_books_client.requests.get")
    def test_fetch_cover_by_isbn_fail_scenarios(self, mock_get):
        """異常なレスポンスや通信エラー時に適切に None を返すか"""
        mock_get.return_value.status_code = 404
        self.assertIsNone(fetch_cover_by_isbn("1234567890"))

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"totalItems": 0}
        self.assertIsNone(fetch_cover_by_isbn("1234567890"))

        mock_get.side_effect = requests.RequestException()
        self.assertIsNone(fetch_cover_by_isbn("1234567890"))

    @patch("books.integrations.openbd.requests.get")
    def test_fetch_openbd_success(self, mock_get):
        """openBD APIから書籍データを取得できるか"""

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"summary": {"title": "テスト本"}}]

        result = fetch_openbd("9784274217883")

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["summary"]["title"], "テスト本")

    @patch("books.integrations.openbd.requests.get")
    def test_fetch_openbd_network_error(self, mock_get):
        """openBD通信エラー時に None を返すか"""

        mock_get.side_effect = requests.RequestException("API Error")

        result = fetch_openbd("0000000000")

        self.assertIsNone(result)


class BookIsbnLookupTest(TestCase):
    """views.isbn_lookup のロジック検証"""

    def test_isbn_lookup_normalization(self):
        """ISBN検索時にハイフン等が正しく正規化されてAPIに渡されるか"""
        url = reverse("books:isbn_lookup")
        input_isbn = "978-4-274-21788-3"

        with patch("books.views.fetch_book_by_isbn") as mock_fetch:
            mock_fetch.return_value = {"title": "テスト本"}
            response = self.client.get(url, {"isbn": input_isbn})

            mock_fetch.assert_called_once_with("9784274217883")
            self.assertEqual(response.status_code, 200)


class BookImportServiceTest(TestCase):
    """外部データ取り込みロジックの検証"""

    @patch("books.services.book_import_service.fetch_openbd")
    def test_fetch_book_by_isbn_with_onix_fallback(self, mock_fetch):
        """summaryにタイトルがない場合、ONIX階層から正しく抽出できるか"""

        onix_title = "ONIXタイトル"
        mock_fetch.return_value = [
            {
                "summary": {},
                "onix": {
                    "DescriptiveDetail": {
                        "TitleDetail": {
                            "TitleElement": {"TitleText": {"content": onix_title}}
                        }
                    }
                },
            }
        ]

        result = book_import_service.fetch_book_by_isbn("1234567890")

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], onix_title)

    @patch("books.services.book_import_service.fetch_openbd")
    def test_fetch_book_by_isbn_unknown_fallback(self, mock_fetch):
        """タイトル情報が完全に欠落している場合、デフォルト値が返るか"""

        mock_fetch.return_value = [{"summary": {}, "onix": {}}]

        result = book_import_service.fetch_book_by_isbn("1234567890")

        self.assertEqual(result["title"], "タイトル不明")

    def test_resolve_cover_fallback_to_google_books(self):
        """カバー画像が未設定時、ISBNベースのGoogle Books URLが生成されるか"""

        isbn = "1234567890"

        url = _resolve_cover(isbn, {})

        self.assertIn(f"ISBN{isbn}", url)


class UtilsUnitTest(TestCase):
    """ユーティリティ関数（日付・テキスト処理）の検証"""

    def test_format_date(self):
        """日付フォーマット変換の検証"""
        self.assertIsNone(date.format_date(None))
        self.assertIsNone(date.format_date(""))
        self.assertIsNone(date.format_date("2026"))

        self.assertEqual(date.format_date("202605"), "2026-05-01")
        self.assertEqual(date.format_date("20260520"), "2026-05-20")

    def test_format_author(self):
        """著者名クレンジングの検証"""
        self.assertIsNone(text.format_author(None))
        self.assertEqual(text.format_author("  "), "")

        self.assertEqual(text.format_author("秋月紅羽"), "秋月紅羽")
        self.assertEqual(text.format_author("秋月,紅羽"), "秋月紅羽")
        self.assertEqual(text.format_author("秋月／紅羽"), "秋月紅羽")

        self.assertEqual(text.format_author("秋月紅羽 冬森朔"), "秋月紅羽、冬森朔")
        self.assertEqual(text.format_author("秋月紅羽、冬森朔"), "秋月紅羽、冬森朔")
