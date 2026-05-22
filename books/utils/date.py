def format_date(pubdate: str | None) -> str | None:
    if not pubdate:
        return None

    # APIから取得した出版日（文字列）を、DjangoのDateFieldが受け付ける「YYYY-MM-DD」形式に整形する

    # 例: "202605"（年月のみ）の場合は、該当月の「1日」として補完する
    if len(pubdate) == 6:
        return f"{pubdate[:4]}-{pubdate[4:6]}-01"

    # 例: "20260520"（年月日）の場合
    if len(pubdate) == 8:
        return f"{pubdate[:4]}-{pubdate[4:6]}-{pubdate[6:8]}"

    return None
