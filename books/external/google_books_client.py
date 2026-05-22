import requests


def fetch_cover_by_isbn(isbn: str):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        res = requests.get(url, timeout=5)

        if res.status_code != 200:
            return None

        items = res.json().get("items")
        if not items:
            return None

        cover = items[0].get("volumeInfo", {}).get("imageLinks", {}).get("thumbnail")

        if cover:
            return cover.replace("http://", "https://")

    except requests.RequestException:
        return None

    return None
