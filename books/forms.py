from django import forms
from django.db.models import IntegerField, Case, When
from django.db.models.functions import Cast, Substr
from .models import Book, Borrow, Location, Review


class BookForm(forms.ModelForm):
    """書籍の登録・編集用フォーム"""

    publication_date = forms.DateField(
        label="出版日",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    purchase_date = forms.DateField(
        label="購入日",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Book
        fields = (
            "isbn",
            "title",
            "author",
            "cover_image_url",
            "publication_date",
            "purchase_date",
            "location",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].empty_label = "場所を選択してください"
        self.fields["location"].required = True

        if "location" in self.fields:
            # 保管場所の選択肢を「階数順（地上階は昇順、地下階は降順）」に並べるための特殊なソート処理
            # 例: 「B2, B1, 1F, 2F」の順に並ぶよう、文字列の「B1」などを一時的に数値（-1など）に変換してアノテーションを付与
            self.fields["location"].queryset = Location.objects.annotate(
                sort_floor=Case(
                    When(
                        name__startswith="B",
                        then=Cast(Substr("name", 2), output_field=IntegerField()) * -1,
                    ),
                    default=Cast("name", output_field=IntegerField()),
                    output_field=IntegerField(),
                )
            ).order_by("-sort_floor")


class BorrowForm(forms.ModelForm):
    """貸出手続き用フォーム"""

    borrowed_at = forms.DateField(
        label="貸出開始日",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Borrow
        fields = ("borrowed_at",)


class ReviewForm(forms.ModelForm):
    """書籍レビュー投稿用フォーム"""

    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {
            "comment": forms.Textarea(
                attrs={
                    "placeholder": "2文字以上で入力してください",
                }
            ),
            "rating": forms.Select(),
        }

    def clean_rating(self):
        """評価値のバリデーション"""
        rating = self.cleaned_data.get("rating")
        if rating is None:
            raise forms.ValidationError("評価は必須です")
        return rating

    def clean_comment(self):
        """コメント内容のバリデーションと整形"""
        comment = self.cleaned_data.get("comment")
        if not comment:
            raise forms.ValidationError("コメントは必須です")

        comment = comment.strip()

        if len(comment) < 2:
            raise forms.ValidationError("コメントは2文字以上入力してください")

        return comment
