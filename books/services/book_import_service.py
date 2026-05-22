from ..external.google_books_client import fetch_cover_by_isbn
from ..integrations.openbd import fetch_openbd
from ..utils.date import format_date
from ..utils.text import format_author


def fetch_book_by_isbn(isbn: str):
    data = fetch_openbd(isbn)

    if not data or data[0] is None:
        return None

    book_data = data[0]
    summary = book_data.get("summary", {})

    title = summary.get("title")
    if not title:
        try:
            title = book_data["onix"]["DescriptiveDetail"]["TitleDetail"][
                "TitleElement"
            ]["TitleText"]["content"]
        except (KeyError, TypeError):
            title = "タイトル不明"

    return {
        "title": title,
        "author": format_author(summary.get("author") or ""),
        "publication_date": format_date(summary.get("pubdate")),
        "cover_image_url": _resolve_cover(isbn, summary),
    }


def _resolve_cover(isbn, summary):
    cover = summary.get("cover")
    if cover:
        return cover

    cover = fetch_cover_by_isbn(isbn)
    if cover:
        return cover

    return (
        f"https://books.google.com/books/content"
        f"?vid=ISBN{isbn}&printsec=frontcover&img=1&zoom=1"
    )
