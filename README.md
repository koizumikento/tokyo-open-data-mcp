# tokyo-open-data-mcp

東京都オープンデータAPIの車椅子対応トイレを、緯度・経度から距離順に探せます。オストメイト設備がある施設に絞り込めます。

[uv](https://docs.astral.sh/uv/) と Git が必要です。Python 3.12以上に対応しています。APIキーは不要です。

## MCPクライアントに登録する

### Codex

```sh
codex mcp add tokyo-open-data-mcp -- uvx --python 3.12 --from git+https://github.com/koizumikento/tokyo-open-data-mcp.git@main tokyo-open-data-mcp
codex mcp list
```

新しいセッションで `/mcp` を開いて接続を確認できます。デスクトップ版ではMCP設定画面で、下のJSON例と同じコマンド・引数を指定できます。

### Claude Desktop / Cursor

- Claude Desktop（Windows） `%APPDATA%/Claude/claude_desktop_config.json`
- Claude Desktop（macOS） `~/Library/Application Support/Claude/claude_desktop_config.json`
- Cursor `.cursor/mcp.json`（プロジェクト内）

設定ファイルの `mcpServers` に項目を追加して、クライアントを再起動してください。`uvx` が見つからない場合は実行ファイルの絶対パスを指定します。

```json
{
  "mcpServers": {
    "tokyo-open-data-mcp": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/koizumikento/tokyo-open-data-mcp.git@main",
        "tokyo-open-data-mcp"
      ]
    }
  }
}
```

> 新宿駅付近の車椅子対応トイレで、オストメイト設備がある場所を3件探して。

## MCPツール

### `find_accessible_toilets`

`latitude` と `longitude` に基準地点の座標を指定します。`require_ostomate` を有効にすると、設備ありと掲載された施設だけを返します。距離は直線距離です。APIのデータ更新日を `updated_at` で返します。確認時の更新日は2021年12月で、現在の設備や利用可否は施設の案内で確認してください。

## CLIで使う

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/tokyo-open-data-mcp.git@main tokyo-open-data-mcp find-accessible-toilets --latitude 35.6936 --longitude 139.7036 --limit 3
```

結果は標準出力にUTF-8のJSONで返ります。

## Pythonから呼び出す

```sh
git clone https://github.com/koizumikento/tokyo-open-data-mcp.git
cd tokyo-open-data-mcp
uv sync --locked
```

```python
import asyncio

from tokyo_open_data_mcp import find_accessible_toilets

print(asyncio.run(find_accessible_toilets(35.6936, 139.7036, limit=3)))
```

既にイベントループがある場合は関数を直接 `await` してください。

## 出典と利用条件

コードはMIT Licenseです。東京都「車椅子使用者対応トイレのバリアフリー情報」を取得し、距離の計算と絞り込みを行っています。[公式API](https://portal.data.metro.tokyo.lg.jp/opendata-api/)・[東京都オープンデータ利用規約](https://portal.data.metro.tokyo.lg.jp/terms/)

## 開発

```sh
uv sync --locked
uv run ruff check .
uv run ty check
uv run pytest
uv build
```
