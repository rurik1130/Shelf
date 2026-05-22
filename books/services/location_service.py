from ..models import Location


def create_location(name: str) -> Location:
    """新規に保管場所を作成する"""
    location = Location(name=name)
    location.save()
    return location


def update_location(location: Location, name: str) -> Location:
    """保管場所の名前を更新する"""
    location.name = name
    location.save()
    return location


def delete_location(location: Location) -> tuple[bool, str | None]:
    """保管場所を削除する 本が紐づいている場合は削除せず、エラーメッセージを返す"""
    if location.book_set.exists():
        return False, "この保管場所には本が登録されているため、削除できません"

    location.delete()
    return True, None
