"""第3回: エージェントに持たせるツール。

ここに書いた関数の docstring と型ヒントが、そのままモデルへの「ツールの説明文」になる。
説明文を書き換えると、モデルがツールを使うかどうか・どんな引数で呼ぶかが変わる。
"""

import json
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAX_RESULTS = 3


@cache
def load_glossary() -> list[dict]:
    with open(DATA_DIR / "glossary.json", encoding="utf-8") as f:
        return json.load(f)["terms"]


def _normalize(text: str) -> str:
    return text.casefold().replace(" ", "").replace("　", "")


def _names(entry: dict) -> list[str]:
    return [_normalize(entry["term"]), _normalize(entry["id"])] + [
        _normalize(a) for a in entry["aliases"]
    ]


def search_glossary(query: str) -> str:
    """学習者へのヒントや確認問題を作る前に、講座の用語の根拠を調べる。

    定義・関連する回・関連語を最大3件返す。部分一致にも対応するので、
    比較質問では共通する短いキーワードで両方の用語をまとめて探す。
    最初の検索後は結果の lecture を使って get_lecture_summary を呼び、
    講義の要点を読んでから、違いの理由となる別の用語をこのツールで検索する。
    返された定義をそのまま回答にせず、短い例や一つの問いを作る材料にする。
    見つからなければ「用語集にはない」と伝え、講座の事実を推測で補わない。

    Args:
        query: 中心となる用語、または比較する用語に共通するキーワードを一つ指定する。
            質問文全体や複数の用語をまとめて渡さない。
            例: 「LoRAとQLoRAの違いは？」なら "LoRA" で両方を検索する。
            講義要約の確認後は "量子化" で違いの理由を調べる。
            両方の用語が返っている場合に "QLoRA" を追加検索する必要はない。

    Returns:
        一致した用語の定義・関連する回・関連語を含むJSON文字列。
        空の検索語や一致する用語がない場合は、その旨を伝える文字列。
    """
    q = _normalize(query)
    if not q:
        return "検索語が空です。調べたい用語を1つ指定してください。"
    glossary = load_glossary()

    exact = [e for e in glossary if q in _names(e)]
    # 「r」のような短い別名が何にでも当たらないよう、名前側が短いものは除く
    partial = [
        e for e in glossary
        if e not in exact and any(q in n or (len(n) >= 3 and n in q) for n in _names(e))
    ]
    in_definition = [
        e for e in glossary
        if e not in exact and e not in partial and q in _normalize(e["definition"])
    ]
    hits = (exact + partial + in_definition)[:MAX_RESULTS]

    if not hits:
        return f"用語集に「{query}」は見つかりませんでした。"
    return json.dumps(
        [
            {
                "term": e["term"],
                "lecture": e["lecture"],
                "definition": e["definition"],
                "related": e["related"],
            }
            for e in hits
        ],
        ensure_ascii=False,
    )


def get_lecture_summary(lecture: int) -> str:
    """指定した回（1始まりの整数）の講義の要点を返す。

    回の内容を聞かれたときに加え、用語の比較や仕組みの質問でも、
    search_glossary が返した lecture を使って必ず講義の背景を確認する。
    例: LoRA と QLoRA の比較では lecture=2 を指定し、結果を読んでから
    search_glossary(query="量子化") で比較の鍵となる用語を確認する。

    Args:
        lecture: 用語の検索結果に含まれる回番号を1始まりの整数で指定する。
    """
    path = DATA_DIR / "lectures" / f"{lecture:02d}.md"
    if not path.exists():
        available = sorted(p.stem for p in (DATA_DIR / "lectures").glob("*.md"))
        return f"第{lecture}回の要点はまだありません。用意されている回: {', '.join(available)}"
    return path.read_text(encoding="utf-8")
