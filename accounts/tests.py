from django.contrib.auth.forms import AuthenticationForm
from django.test import TestCase
from django.urls import reverse

from .models import User


class UserManagerTest(TestCase):
    """ユーザーモデルの作成ロジック検証"""

    def test_create_user(self):
        """通常のユーザー作成が正しく行われるか"""

        username = "testuser"
        email = "test@example.com"
        password = "test12345"

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        self.assertEqual(user.username, username)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)

    def test_create_superuser(self):
        """スーパーユーザー作成時に権限が正しく付与されるか"""

        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test12345",
        )

        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)


class SignUpTest(TestCase):
    """サインアップ機能のバリデーションと登録検証"""

    def setUp(self):
        self.signup_url = reverse("accounts:signup")
        self.success_url = reverse("books:book_list")

    def test_signup_page_display(self):
        """サインアップ画面が正しく表示されるか"""
        response = self.client.get(self.signup_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/signup.html")

    def test_signup_success(self):
        """正常な入力でユーザー登録と自動ログインができるか"""

        username = "newuser"
        signup_data = {
            "username": username,
            "last_name": "test",
            "first_name": "テスト",
            "email": "test@example.com",
            "password1": "test12345",
            "password2": "test12345",
        }

        response = self.client.post(self.signup_url, data=signup_data, follow=True)

        self.assertTrue(User.objects.filter(username=username).exists())
        self.assertRedirects(response, self.success_url)
        self.assertTrue(response.context["user"].is_authenticated)

    def test_signup_password_mismatch(self):
        """パスワード不一致でエラーになり、ユーザーが作成されないか"""

        invalid_data = {
            "username": "badpassuser",
            "password1": "test12345",
            "password2": "test67890",
        }

        response = self.client.post(self.signup_url, data=invalid_data)

        self.assertFalse(User.objects.filter(username="badpassuser").exists())
        self.assertIn("form", response.context)
        self.assertFalse(response.context["form"].is_valid())

    def test_signup_invalid_data(self):
        """必須項目が欠けている場合にエラーになり、画面が再表示されるか"""
        invalid_data = {"username": ""}

        response = self.client.post(self.signup_url, data=invalid_data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())


class LoginLogoutTest(TestCase):
    """ログイン・ログアウトの基本機能の検証"""

    def setUp(self):
        self.username = "loginuser"
        self.password = "testpass12345"
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
        )
        self.login_url = reverse("accounts:login")
        self.logout_url = reverse("accounts:logout_confirm")
        self.success_url = reverse("books:book_list")

    def test_login_page_display(self):
        """ログイン画面の表示確認"""
        response = self.client.get(self.login_url)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], AuthenticationForm)

    def test_login_success(self):
        """正常ログインとリダイレクト確認"""

        response = self.client.post(
            self.login_url,
            data={"username": self.username, "password": self.password},
            follow=True,
        )

        self.assertTrue(response.context["user"].is_authenticated)
        self.assertRedirects(response, self.success_url)

    def test_login_invalid_credentials(self):
        """間違ったパスワードでログインに失敗するか"""

        response = self.client.post(
            self.login_url,
            data={"username": self.username, "password": "wrongpassword"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())
        self.assertFalse(response.context["user"].is_authenticated)

    def test_login_redirect_with_next_param(self):
        """nextパラメータがある場合、ログイン後にそのURLへリダイレクトされるか"""
        target_url = reverse("books:book_list")
        url_with_next = f"{self.login_url}?next={target_url}"

        response = self.client.post(
            url_with_next,
            data={"username": self.username, "password": self.password},
            follow=True,
        )

        self.assertRedirects(response, target_url)

    def test_logout_page_display_get(self):
        """ログアウト確認画面（GETリクエスト）が正しく表示されるか"""

        response = self.client.get(self.logout_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/logout.html")

    def test_logout_execution(self):
        """ログアウトの実行とリダイレクト確認"""

        # テスト環境のブラウザ（Client）でログイン状態を作ってからログアウトを叩く
        self.client.login(username=self.username, password=self.password)

        response = self.client.post(self.logout_url, follow=True)

        self.assertFalse(response.context["user"].is_authenticated)
        self.assertRedirects(response, self.login_url)
