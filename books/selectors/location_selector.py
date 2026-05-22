from django.db.models import Count, IntegerField, Case, When
from django.db.models.functions import Cast, Substr
from django.shortcuts import get_object_or_404
from ..models import Location


def get_location_list_with_book_count():
    """保管場所の一覧を、紐づいている本の冊数付きで取得する（階数順ソート）"""

    return Location.objects.annotate(
        book_count=Count("book"),
        sort_floor=Case(
            When(
                name__startswith="B",
                then=Cast(Substr("name", 2), output_field=IntegerField()) * -1,
            ),
            default=Cast("name", output_field=IntegerField()),
            output_field=IntegerField(),
        ),
    ).order_by("-sort_floor")


def get_location_by_id(location_id: int) -> Location:
    """特定の保管場所を取得する"""
    return get_object_or_404(Location, id=location_id)
