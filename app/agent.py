"""第3回: Pydantic AI で作る学習支援エージェント。

使い方:
    uv run python -m app.agent "AIE2026の講座で使う「lecNN-start タグ」とは何ですか？"
    uv run python -m app.agent --trace "LoRAとQLoRAの違いは？"   # ツール呼び出しを表示
    uv run python -m app.agent --mcp --trace "LoRAとは？"        # 第5回: ツールを MCP サーバーから受け取る
    uv run python -m app.agent --mcp --list-tools               # 第5回: モデルに見えるツール一覧（APIキー不要）

エージェント = モデル + ループ + ツール。
モデルは tools.py の関数を「ツール」として呼び出し、その結果を見て回答を作る。
第5回では、同じツールを MCP サーバー（app/mcp_server.py）経由で受け取る。
"""

import argparse
import inspect
import json
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from fastmcp import Client
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.google import GoogleProvider

from app import tools
from app.config import MODEL, api_error_message, get_api_key

INSTRUCTIONS = """\
あなたはAIエンジニアリング講座（AIE2026）の「問いかける学習コーチ」です。
目標は知識を説明しきることではなく、学習者が自分の言葉で考え、理解を確かめることです。

根拠の確認:
- 用語や講座に固有の内容は、次の順番で調べてから応答する。
  1. search_glossary で中心となるキーワードを一つ検索する。比較質問では、
     共通する短い語を使い、一度の検索で両方の用語が返れば個別検索を繰り返さない。
  2. 検索結果の lecture を読み、その回を get_lecture_summary で確認する。
     用語の比較でも必ず講義の要点を確認し、検索結果を受け取ってからこのツールを呼ぶ。
  3. 講義の要点を読んでから、比較の理由を理解する鍵となる別の用語を
     search_glossary で一つ検索する。既に調べた語は再検索しない。
- 「LoRAとQLoRAの違いは？」では、search_glossary(query="LoRA") の結果に
  両方の用語が含まれることを確認し、get_lecture_summary(lecture=2) で背景を調べ、
  その結果を読んでから search_glossary(query="量子化") で違いの理由を確認する。
  この3段階を順番に実行し、QLoRA の個別検索は結果に含まれない場合だけ行う。
- 回だけを指定した質問では get_lecture_summary から始め、必要な用語を検索する。
- ツールで確認できた講座の事実と、あなたが作る練習用の例を区別する。
- 最初の検索で見つからない場合は「用語集にはない」と明記し、回を推測せず、
  検索語を確認する問いを一つ返す。他のツールでも根拠が
  得られなければ、講座の内容や関係する回を推測せず、確認したい語句や回を一つ尋ねる。

教え方:
- 初めての質問には、定義や正解をすぐに提示しない。短い身近な例か対比を一つ出し、
  学習者の予想を尋ねる。学習者がすでに考えを書いていれば、その内容から始める。
- 一度の応答で扱う論点は一つ、質問も必ず一つに絞る。
- 学習者の考えがあれば、合っている点を具体的に一つ示し、誤解があれば責めずに
  修正の手がかりを一つ渡す。根拠なく「正解」と褒めない。
- 「分からない」と言われたら、説明を長くせず、二択の問いと小さなヒントを出す。
- 明確に説明を求められた場合は、要点を最大3文で説明した後、理解を確かめる問いを出す。
- 宿題では、提出できる完成回答や完成コードを渡さない。次に試す操作や考え方を
  一つだけ示し、学習者自身の予想や実行結果を尋ねる。

出力形式:
- 日本語で、原則200字以内。長い講義や網羅的な箇条書きは避ける。
- 「手がかり:」「関連回:」「問い:」の順で出力し、最後は一つの質問で終える。
- 関連回はツールで確認できた第N回を記載する。確認できない場合は「未確認」とする。
"""

# モデルは実行時に渡す（テストではAPIを呼ばない TestModel に差し替えるため）
agent = Agent(instructions=INSTRUCTIONS)
agent.tool_plain(tools.search_glossary)
agent.tool_plain(tools.get_lecture_summary)

# TODO(第3回 演習): tools.py に make_quiz を作り、ここで登録しよう

# 第5回: 使う MCP サーバーの設定ファイル。Claude Desktop や Cursor と同じ "mcpServers" 形式
MCP_CONFIG = Path(__file__).resolve().parent / "mcp_servers.json"


def load_mcp_servers(config_path: Path = MCP_CONFIG) -> list[MCPToolset]:
    """設定ファイル（mcpServers 形式）を読み、サーバーごとに接続（MCPToolset）を作る。

    - "command" があれば stdio：サーバーをサブプロセスとして起動する
    - "url" があれば Streamable HTTP：起動済みのサーバーに接続する
    ツール名には「サーバー名_」を付ける（例: glossary_search_glossary）。複数のサーバーに
    同じ名前のツールがあっても区別できるようにするため。

    Pydantic AI には同じことをする load_mcp_toolsets() もある。ここで自分で組み立てているのは、
    古い SDK で作られたサーバー（fetch など）につなぐとき、接続方式の自動判定（"auto"）が
    警告を大量に出すため。"legacy" に固定すると新旧どちらのサーバーにも静かにつながる。
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))["mcpServers"]
    toolsets = []
    for name, spec in config.items():
        if "url" in spec:
            transport = spec["url"]
        else:
            transport = StdioTransport(spec["command"], spec.get("args", []), env=spec.get("env"))
        toolsets.append(MCPToolset(Client(transport, mode="legacy")).prefixed(name))
    return toolsets


def build_mcp_agent(config_path: Path = MCP_CONFIG) -> Agent:
    """第5回: 関数を直接登録する代わりに、MCP サーバーが公開するツールを使うエージェント。INSTRUCTIONS は同じ。"""
    return Agent(instructions=INSTRUCTIONS, toolsets=load_mcp_servers(config_path))


def build_model() -> GoogleModel:
    return GoogleModel(MODEL, provider=GoogleProvider(api_key=get_api_key()))


def print_tools(target: Agent) -> None:
    """モデルに見えているツールの一覧（名前・説明文・引数）を表示する。LLM は呼ばない。

    TestModel（テストで使う偽モデル）にツール一覧を渡し、そこから読み出す。
    MCP サーバーのツールも、第3回の関数ツールも、モデルから見れば同じ形をしている。
    """
    model = TestModel(call_tools=[])
    target.run_sync("ツール一覧", model=model)
    tools_seen = model.last_model_request_parameters.function_tools
    print(f"モデルに見えているツール: {len(tools_seen)} 個")
    for tool in tools_seen:
        print(f"\n[{tool.name}]")
        print("  " + inspect.cleandoc(tool.description or "").replace("\n", "\n  "))
        params = tool.parameters_json_schema.get("properties", {})
        print(f"  引数: {json.dumps(params, ensure_ascii=False)}")


def print_trace(result) -> None:
    """どのツールが、どの引数で呼ばれ、何を返したかを表示する。"""
    print("\n--- trace ---")
    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                print(f"[tool call]   {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                print(f"[tool return] {part.tool_name} -> {str(part.content)[:120]}…")
    print(f"[usage] {result.usage}")


def main() -> None:
    parser = argparse.ArgumentParser(description="学習支援エージェントに質問する")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--trace", action="store_true", help="ツール呼び出しを表示する")
    parser.add_argument("--mcp", action="store_true", help="第5回: ツールを MCP サーバー（app/mcp_servers.json）から受け取る")
    parser.add_argument("--list-tools", action="store_true", help="モデルに見えるツール一覧を表示して終了する（APIキー不要）")
    args = parser.parse_args()

    target = build_mcp_agent() if args.mcp else agent
    if args.list_tools:
        print_tools(target)
        return
    if not args.question:
        parser.error("質問を指定してください")

    print(f"[model] {MODEL}")
    if args.mcp:
        print("[tools] MCP サーバー（app/mcp_servers.json）")
    try:
        result = target.run_sync(args.question, model=build_model())
    except ModelHTTPError as e:
        print(api_error_message(e.status_code, str(e.body)[:200]))
        raise SystemExit(1)
    print(result.output)
    if args.trace:
        print_trace(result)


if __name__ == "__main__":
    main()
