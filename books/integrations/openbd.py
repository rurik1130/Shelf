import logging
import requests


def fetch_openbd(isbn: str):
    isbn = isbn.replace("-", "").strip()
    url = f"https://api.openbd.jp/v1/get?isbn={isbn}"
    logger = logging.getLogger(__name__)

    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()

        if data is None or (
            isinstance(data, list) and (len(data) == 0 or data[0] is None)
        ):
            return None

        return data
    except requests.RequestException as e:
        logger.error(f"ISBN {isbn} fetch error: {e}")
        return None
