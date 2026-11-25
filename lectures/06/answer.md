# 第6回 解答

## 演習

- MCP なしでは `search_materials`、MCP 経由では `glossary_search_glossary`、`glossary_get_lecture_summary`、`fetch_fetch` が表示された。
- 「3レベル」の質問では `glossary_search_glossary({'query': '3レベル'})` が呼ばれ、モデル応答は2回だった。
- `get_lecture_summary` を MCP に公開した。「第2回では何を学びますか？」と聞くと `glossary_get_lecture_summary({'lecture': 2})` が呼ばれ、モデル応答は2回だった。
- fetch を設定に追加すると、`fetch_fetch({'url': 'https://modelcontextprotocol.io/'})` でページを取得し、日本語3行に要約できた。

## 宿題

- 取り組んだレベル：基礎
- やったこと：glossary を stdio から HTTP 接続に変更した。その後、`search_glossary` の docstring を書き換え、同じ「3レベル」の質問で比べた。

### 接続方法の違い

| 項目 | stdio | Streamable HTTP |
| --- | --- | --- |
| 起動 | クライアントがサーバーを起動する | 別ターミナルで `uv run python -m app.mcp_server --http` を実行する |
| プロセス | クライアントが子プロセスとして管理する | サーバーを別に起動・停止する |
| 通信 | 標準入力・標準出力。ポート不要 | `http://127.0.0.1:8000/mcp` に接続。ポート8000を使う |

接続方法を変えても、表示されるツールは同じ3個だった。fetch は stdio のまま使った。

### docstring を変えた結果

説明文に「宿題の『3レベル』の質問には query に『3レベル』を指定して使う」と書き、HTTP サーバーを再起動した。`--list-tools` には新しい説明文が表示され、ツール名と引数は変わらなかった。

| 条件 | 呼ばれたツール | モデル応答 | 時間 |
| --- | --- | ---: | ---: |
| stdio・変更前 | 用語集、fetch、第1回要約 | 4回 | 10.44秒 |
| HTTP・変更前 | 用語集、fetch、第1回要約 | 4回 | 16.35秒 |
| HTTP・変更後 | 用語集だけ | 2回 | 5.03秒 |

変更前の fetch は404になったが、最終回答はできた。変更後は `glossary_search_glossary({'query': '3レベル'})` だけで回答できた。どの条件でも「基礎・実装・発展のどれか1つに取り組めば宿題完了」と答えた。

- 気づき：ツールの説明を具体的にすると、今回の実行では余分な外部アクセスが減った。
