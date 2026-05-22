import re


def format_author(author: str | None) -> str | None:
    if not author:
        return author

    # 外部APIの著者名に含まれる様々な区切り文字（スペース、全角スラッシュ等）を、画面表示用に「、」へ統一する
    authors = re.split(r"[、\s]+", author.strip())
    formatted = []

    for a in authors:
        if not a:
            continue

        # 既に姓名の間にスペースが入っている外国語名などはそのままスルーする
        if " " in a:
            formatted.append(a)
            continue

        # 例: 「(著者名)／著」や「(著者名A), (著者名B)」のようにAPIから返ってくるパターンへの対処
        a = a.replace("／", ",")
        parts = a.split(",")

        # 「著者名, 役割（著/訳など）」に分解できる場合は、文字列を結合して「(著者名)著」にする
        if len(parts) >= 2:
            formatted.append(f"{parts[0].strip()}{parts[1].strip()}")
        else:
            formatted.append(a.strip())

    return "、".join(formatted)
