from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render

from .forms import CustomUserCreationForm


def signup(request):
    """新規ユーザー登録を行い、自動ログイン後に本一覧へ遷移する"""
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # 登録後、そのままログイン状態にする
            return redirect("books:book_list")
    else:
        form = CustomUserCreationForm()

    return render(request, "registration/signup.html", {"form": form})


def login_view(request):
    """ユーザーログイン処理。ログイン後は元のページ（next）または本一覧へ遷移する"""
    # ログイン制限がかかったページから遷移してきた場合の戻り先URLを取得
    next_url = request.GET.get("next") or request.POST.get("next")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(next_url or "books:book_list")
    else:
        form = AuthenticationForm()

    return render(request, "registration/login.html", {"form": form})


def logout_view(request):
    """ログアウト処理 セキュリティ（CSRF対策）のためPOSTのみ受け付ける"""
    if request.method == "POST":
        logout(request)
        return redirect("accounts:login")

    # GETアクセスの場合は確認画面を表示
    return render(request, "registration/logout.html")
