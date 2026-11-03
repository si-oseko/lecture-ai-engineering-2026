# コンテキスト変更前後の比較

## 変更内容

ツールの使い方に変化が出るよう、`app/agent.py` の `INSTRUCTIONS` と `app/tools.py` の両ツールの docstring を編集した。

- `INSTRUCTIONS`：用語を直接説明する指示から、用語検索・講義要約の確認・関連語の検索を順番に行い、短い手がかりと問いを返す指示に変更した。
- `search_glossary` の docstring：用語ごとの個別検索から、共通キーワードによる検索と、講義要約を読んだ後の関連語検索を促す説明に変更した。
- `get_lecture_summary` の docstring：回の内容を聞かれた場合だけでなく、用語の比較でも検索結果の回番号を使って参照する説明に変更した。

## 実行方法

編集前と編集後に、同じ質問をそれぞれ `--trace` 付きで実行した。以下はターミナルの実行ログをもとにした記録。

```powershell
uv run python -m app.agent --trace "LoRAとQLoRAの違いは？"
uv run python -m app.agent --trace "AIE2026の講座の宿題にある「3レベル」とは何ですか？"
```

モデルは `gemini-3.5-flash-lite`。モデルとツールの検索処理は変更せず、指示文と説明文を変更して比較した。

## ツールの呼ばれ方の比較

「LoRAとQLoRAの違いは？」では、次の順序を指定している。

1. `search_glossary(query="LoRA")`：部分一致で LoRA と QLoRA をまとめて検索。
2. `get_lecture_summary(lecture=2)`：検索結果の回番号で講義の背景を確認。
3. `search_glossary(query="量子化")`：講義要約を読んだ後、違いの理由を確認。

ターミナルの最新ログで、上記の3段階の呼び出しを確認した。

| 質問 | 比較項目 | 編集前 | 編集後 |
| --- | --- | --- | --- |
| LoRAとQLoRAの違い | ツールの種類 | 1種類 | 2種類 |
| 同上 | ツール呼び出し（`tool_calls`） | 2回 | 3回 |
| 同上 | モデルへのリクエスト（`requests`） | 2回 | 4回 |
| 宿題の3レベル | ツールの種類 | 1種類 | 2種類 |
| 同上 | ツール呼び出し（`tool_calls`） | 1回 | 2回 |
| 同上 | モデルへのリクエスト（`requests`） | 2回 | 3回 |

### LoRAとQLoRAの実行ログ

編集前：

```text
[tool call] search_glossary({'query': 'LoRA'})
[tool call] search_glossary({'query': 'QLoRA'})
requests=2, tool_calls=2
```

編集後：

```text
[tool call] search_glossary({'query': 'LoRA'})
[tool call] get_lecture_summary({'lecture': 2})
[tool call] search_glossary({'query': '量子化'})
requests=4, tool_calls=3
```

編集前は `LoRA` と `QLoRA` を個別に検索していた。
編集後は `LoRA` の検索結果で両方を確認し、講義要約と `量子化` の検索を追加した。
編集前の回答は、LoRAでは更新分だけを学習し、QLoRAではベースモデルの重みを量子化する、という違いを箇条書きで説明し、「関係する回：第2回」で終わっていた。

編集後の回答は短い手がかりを示し、次の問いで終わった。

> ベースモデルの重みを4ビットに縮めることで、LoRA単体と比べてどんなメリットが生まれると思いますか？

### 宿題の3レベルの実行ログ

編集前：

```text
[tool call] search_glossary({'query': '3レベル'})
requests=2, tool_calls=1
```

編集後：

```text
[tool call] search_glossary({'query': '3レベル'})
[tool call] get_lecture_summary({'lecture': 1})
requests=3, tool_calls=2
```

編集前の回答は「基礎：講義内容の確認」「実装：自分でコードを書く」「発展：調査や試行」を列挙し、どれか一つに取り組めば完了することを説明していた。

編集後の回答は次のとおり。

> 手がかり：AIE2026の宿題は「基礎・実装・発展」の3段階に分かれており、どれか1つを選んで取り組む仕組みです。
> 関連回：第1回
> 問い：基礎、実装、発展の3つのレベルのうち、ご自身の今のペースや興味ではどれから取り組んでみたいですか？

この質問では、追加の用語検索までは行われず、用語検索と講義要約の2回だった。
指示した全段階がすべての質問で必ず実行されるわけではないことも分かった。
