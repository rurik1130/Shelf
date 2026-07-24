import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Avg, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme, urlencode

from .domain.limits import is_within_borrow_limit, is_within_reservation_limit
from .domain.status import resolve_status_display
from .forms import BookForm, BorrowForm, ReviewForm
from .models import Book, Borrow, Reservation
from .permissions.borrow_permission import can_borrow, can_reserve, can_return
from .permissions.review_permission import can_review
from .selectors.book_selector import (
    get_active_book_by_id,
    get_book_detail,
    get_book_list_with_user_status,
    get_books_for_list,
)
from .selectors.borrow_selector import get_active_borrow
from .selectors.location_selector import (
    get_location_by_id,
    get_location_list_with_book_count,
)
from .selectors.mypage_selector import get_mypage_data
from .selectors.review_selector import (
    get_review_by_id,
    get_user_review,
    get_user_reviews_with_books,
)
from .services.book_import_service import fetch_book_by_isbn
from .services.book_service import delete_book

from .services.borrow_service import (  # isort: skip
    borrow_book as borrow_book_service,
    return_book as return_book_service,
)
from .services.location_service import create_location, delete_location, update_location
from .services.mypage_service import build_mypage_view_model

from .services.reservation_service import (  # isort: skip
    cancel_reservation as cancel_reservation_service,
    reserve_book as reserve_book_service,
)

from .services.review_service import (  # isort: skip
    delete_review as delete_review_service,
    save_review,
)
from .utils.redirect import get_redirect_response


def is_staff_user(user):
    """ユーザーがスタッフ権限を持っているか判定する"""
    return user.is_staff


@login_required
def book_list(request):
    """本の一覧を表示する（検索・ステータスフィルタリング・Pagination対応） ログインユーザーが「借りている」「予約している」状況に応じたフラグを付与する"""
    query = request.GET.get("q", "")
    status_filter = request.GET.get("status", "")

    books_queryset = get_books_for_list()

    if query:
        books_queryset = books_queryset.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(isbn__icontains=query)
        )

    book_list_data = get_book_list_with_user_status(books_queryset, request.user)

    if status_filter:
        book_list_data = [
            item for item in book_list_data if item["status"] == status_filter
        ]

    paginator = Paginator(book_list_data, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "books/book_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status_filter": status_filter,
        },
    )


@login_required
def book_detail(request, id):
    """本の詳細情報を表示する（貸出・予約・返却の権限判定を含む）"""
    book = get_book_detail(id)
    user = request.user

    active_borrow_count = Borrow.objects.filter(
        user=user, returned_at__isnull=True
    ).count()
    reservation_count = Reservation.objects.filter(user=user).count()

    borrow_limit_reached = not is_within_borrow_limit(active_borrow_count)
    reserve_limit_reached = not is_within_reservation_limit(reservation_count)

    current_borrow = book.get_active_borrow()
    reservation = book.get_first_reservation()

    status_info = resolve_status_display(book)

    can_borrow_flag = can_borrow(
        has_current_borrow=bool(current_borrow),
        reservation_user_id=reservation.user.id if reservation else None,
        user_id=request.user.id,
    )

    can_reserve_flag = can_reserve(
        has_current_borrow=bool(current_borrow),
        has_reservation=bool(reservation),
    )

    can_return_flag = can_return(
        borrow_user_id=current_borrow.user.id if current_borrow else None,
        user_id=request.user.id,
    )

    my_review = None
    if request.user.is_authenticated:
        my_review = get_user_review(book=book, user=request.user)

    reviews = book.review_set.select_related("user").all()

    avg_rating = book.review_set.aggregate(Avg("rating"))["rating__avg"]

    other_reviews = reviews.exclude(user=user) if user.is_authenticated else reviews

    has_borrowed = can_review(book, user)

    return render(
        request,
        "books/book_detail.html",
        {
            "book": book,
            "status_info": status_info,
            "can_borrow": can_borrow_flag,
            "can_reserve": can_reserve_flag,
            "can_return": can_return_flag,
            "borrow_limit_reached": borrow_limit_reached,
            "reserve_limit_reached": reserve_limit_reached,
            "my_review": my_review,
            "other_reviews": other_reviews,
            "avg_rating": avg_rating,
            "has_borrowed": has_borrowed,
        },
    )


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def location_list(request):
    """保管場所の一覧を表示する（スタッフ専用）"""
    locations = get_location_list_with_book_count()
    return render(request, "books/location_list.html", {"locations": locations})


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def location_create(request):
    """新しい保管場所を作成する（スタッフ専用・非同期対応）"""
    if request.method == "POST":
        floor = request.POST.get("floor", "").strip()
        name_part = request.POST.get("name", "").strip()

        if floor and name_part:
            full_name = f"{floor}F {name_part}"
        else:
            full_name = name_part or request.POST.get("name", "").strip()

        # 入力エラー時、リクエストの送信元（SPA/JavaScriptか、通常の画面遷移か）によってレスポンスを切り替える
        if not full_name:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": "場所名が入力されていません"}, status=400)
            messages.error(request, "場所名を入力してください")
            return redirect("books:location_list")

        location = create_location(name=full_name)

        # 本登録画面のモーダル等から非同期で追加された場合はJSON、直接ページから叩かれた場合はリダイレクトする
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"id": location.id, "name": location.name})

        messages.success(request, f"保管場所「{location.name}」を追加しました")
        return redirect("books:location_list")

    return redirect("books:location_list")


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def location_update(request, id):
    """保管場所の名称を編集する（スタッフ専用）"""
    location = get_location_by_id(id)

    if request.method == "POST":
        floor = request.POST.get("floor", "").strip()
        name_part = request.POST.get("name", "").strip()

        if floor and name_part:
            full_name = f"{floor}F {name_part}"
        else:
            full_name = name_part

        if full_name:
            update_location(location, full_name)
            messages.success(request, f"保管場所「{full_name}」を更新しました")
            return redirect("books:location_list")

    # データベースに「3F 資料室」のように結合されて保存されている文字列を、フォームの「フロア（3）」と「エリア（資料室）」の各入力欄に分解して初期値として戻す処理
    match = re.match(r"^([a-zA-Z0-9]+)F\s+(.+)$", location.name)
    if match:
        floor_val = match.group(1)
        clean_name_val = match.group(2)
    else:
        floor_val = ""
        clean_name_val = location.name

    return render(
        request,
        "books/location_form.html",
        {"location": location, "floor": floor_val, "clean_name": clean_name_val},
    )


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def location_delete(request, id):
    """保管場所の削除確認画面、および削除実行（スタッフ専用）"""
    location = get_location_by_id(id)

    if request.method == "POST":
        location_name = location.name

        _success, error = delete_location(location)
        if error:
            messages.error(request, error)
            return redirect("books:location_list")

        messages.success(request, f"保管場所「{location_name}」を削除しました")
        return redirect("books:location_list")

    return render(request, "books/location_confirm_delete.html", {"location": location})


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def book_create(request):
    """新しい本を登録する（スタッフ専用）"""
    if request.method == "POST":
        form = BookForm(request.POST)
        if form.is_valid():
            form.save()
            return get_redirect_response(request, default="/books/")
    else:
        form = BookForm()

    return render(request, "books/book_form.html", {"form": form})


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def book_update(request, id):
    """登録済みの本の情報を編集する（スタッフ専用）"""
    book = get_active_book_by_id(id)

    if request.method == "POST":
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            return get_redirect_response(request, default="/books/")
    else:
        form = BookForm(instance=book)

    return render(request, "books/book_form.html", {"form": form})


@login_required
@user_passes_test(is_staff_user, login_url="/accounts/login/")
def book_delete(request, id):
    """本を削除（論理削除等）する確認画面の表示と実行（スタッフ専用）"""
    book = get_active_book_by_id(id)
    if request.method == "POST":
        delete_book(book)
        return redirect("books:book_delete_complete")
    return render(request, "books/book_confirm_delete.html", {"book": book})


@login_required
def book_delete_complete(request):
    """書籍削除完了画面を表示する"""
    return render(request, "books/book_delete_complete.html")


def isbn_lookup(request):
    """外部API等からISBNを使って本の情報を取得する フロントエンドのJavaScriptからの呼び出しを想定したJSONレスポンスを返す"""
    isbn = request.GET.get("isbn")
    if not isbn:
        return JsonResponse({"error": "isbn required"}, status=400)

    clean_isbn = re.sub(r"[^0-9X]", "", isbn.upper())

    data = fetch_book_by_isbn(clean_isbn)

    if not data:
        return JsonResponse({"error": "not found"}, status=404)

    return JsonResponse(data)


@login_required
def borrow_book(request, id):
    """本を貸し出す処理を実行する"""
    book = get_active_book_by_id(id)
    next_url = request.GET.get("next")

    if request.method == "POST":
        form = BorrowForm(request.POST)
        if form.is_valid():
            borrow, error = borrow_book_service(
                user=request.user,
                book=book,
                borrowed_at=form.cleaned_data["borrowed_at"],
            )
            if error:
                messages.error(request, error)
                return get_redirect_response(request)

            response = redirect("books:borrow_complete", id=borrow.id)
            # 完了画面へリダイレクトした後、さらにその先の元のページ（マイページ等）へ戻れるよう、
            # redirectオブジェクトの遷移先URLに next パラメータを引き継がせる
            if next_url:
                response["Location"] += f"?next={next_url}"
            return response
    else:
        form = BorrowForm()

    return render(
        request,
        "books/borrow_form.html",
        {"form": form, "book": book, "next_url": next_url},
    )


@login_required
def borrow_complete(request, id):
    """貸出完了画面を表示する"""
    borrow = get_object_or_404(Borrow, id=id, user=request.user)

    book = borrow.book
    due_date = borrow.get_due_date()

    next_url = request.GET.get("next")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        next_url = "/"

    return render(
        request,
        "books/borrow_complete.html",
        {
            "book": book,
            "borrow": borrow,
            "due_date": due_date,
            "next_url": next_url,
        },
    )


@login_required
def reserve_book(request, id):
    """本の予約処理を実行する"""
    book = get_active_book_by_id(id)

    reservation, error = reserve_book_service(
        user=request.user,
        book=book,
    )

    if error:
        messages.error(request, error)
        return get_redirect_response(request)

    return redirect("books:reserve_complete", id=reservation.id)


@login_required
def reserve_complete(request, id):
    """予約完了画面を表示する"""
    reservation = get_object_or_404(Reservation, id=id, user=request.user)

    book = reservation.book

    return render(
        request,
        "books/reserve_complete.html",
        {
            "book": book,
            "reservation": reservation,
        },
    )


@login_required
def cancel_reservation(request, id):
    """予約をキャンセルする"""
    book = get_active_book_by_id(id)

    success, error = cancel_reservation_service(
        user=request.user,
        book=book,
    )

    if error:
        messages.error(request, error)

    if not success:
        return get_redirect_response(request)

    return render(
        request,
        "books/reserve_cancel_complete.html",
        {
            "book": book,
        },
    )


@login_required
def return_book(request, id):
    """本の返却処理を実行する"""
    book = get_active_book_by_id(id)
    borrow = get_active_borrow(book, request.user)
    next_url = request.GET.get("next")

    if not borrow:
        return get_redirect_response(request)

    borrow, error = return_book_service(borrow=borrow, user=request.user)

    if error:
        messages.error(request, error)
        return get_redirect_response(request)

    response = redirect("books:return_complete", id=borrow.id)
    if next_url:
        response["Location"] += "?" + urlencode({"next": next_url})
    return response


@login_required
def return_complete(request, id):
    """返却完了画面を表示する"""
    borrow = get_object_or_404(Borrow, id=id, user=request.user)

    book = borrow.book

    next_url = request.GET.get("next")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        next_url = "/"

    return render(
        request,
        "books/return_complete.html",
        {
            "book": book,
            "borrow": borrow,
            "next_url": next_url,
        },
    )


@login_required
def mypage(request):
    """ログインユーザーの貸出中・予約中・レビュー済みの本を一覧表示する"""
    user = request.user

    borrows, reservations, _ = get_mypage_data(user)

    user_reviews = get_user_reviews_with_books(user)

    borrow_list, reservation_list = build_mypage_view_model(
        borrows, reservations, {r.book_id: r for r in user_reviews}
    )

    return render(
        request,
        "books/mypage.html",
        {
            "borrow_list": borrow_list,
            "reservation_list": reservation_list,
            "user_reviews": user_reviews,
        },
    )


@login_required
def add_review(request, id):
    """本に対するレビューを投稿または編集する（過去に一度でも借りたことがあればOK）"""
    book = get_object_or_404(Book, id=id, deleted_at__isnull=True)

    has_borrowed = can_review(book, request.user)

    if not has_borrowed:
        return get_redirect_response(request, default="/")

    existing = get_user_review(book=book, user=request.user)

    form = ReviewForm(request.POST or None, instance=existing)

    if request.method == "POST" and form.is_valid():
        save_review(book=book, user=request.user, form=form)
        return redirect("books:book_detail", id=book.id)

    return render(
        request,
        "books/review_form.html",
        {
            "form": form,
            "book": book,
        },
    )


@login_required
def delete_review(request, id):
    """投稿したレビューを削除する 実行前に確認画面を表示する"""
    review = get_review_by_id(id)
    if request.method == "POST":
        _, error = delete_review_service(review=review, user=request.user)
        if error:
            messages.error(request, error)
            return redirect("books:book_detail", id=review.book.id)

        return redirect("books:review_delete_complete")

    return render(request, "books/review_confirm_delete.html", {"review": review})


@login_required
def review_delete_complete(request):
    """レビュー削除完了画面を表示する"""
    return render(request, "books/review_delete_complete.html")
