# tokyo-open-data-mcp

東京都のオープンデータから、公共施設などや鉄道駅の車椅子使用者対応トイレを緯度・経度で探せます。介助用ベッドやオストメイト設備が必要な場合は、設備条件を指定できます。

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

`latitude` と `longitude` に基準地点の座標を指定します。結果は直線距離順で、`limit` は1〜50件（既定10件）です。

| 引数 | 内容 |
| --- | --- |
| `source_kind` | `facility` は公共施設など、`rail` は鉄道駅。省略すると両方を検索 |
| `require_ostomate` | オストメイト用設備がある |
| `require_ostomate_warm_water` | オストメイト用設備が温水対応 |
| `require_universal_sheet` | 大人も使用できる介助用ベッド（ユニバーサルシート）がある |
| `require_baby_changing_table` | 乳幼児用おむつ交換台等がある |

複数の設備条件を指定すると、すべてを満たすトイレを返します。`○` や `○（注）` のような設備ありの表記を判定し、結果には出典の記号をそのまま表示します。`name` は施設名または駅名です。`toilet_name`、`floor`、鉄道会社・路線、`notes` も確認できます。検索結果の `id` は現行CSVの管理番号などを使った識別子です。

## CLIで使う

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/tokyo-open-data-mcp.git@main tokyo-open-data-mcp find-accessible-toilets --latitude 35.6936 --longitude 139.7036 --source-kind rail --require-universal-sheet --limit 3
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

result = asyncio.run(
    find_accessible_toilets(35.6936, 139.7036, limit=3, require_universal_sheet=True)
)
print(result["items"])
```

既にイベントループがある場合は関数を直接 `await` してください。

## データの更新

東京都のカタログで公開されている2種類のCSVを使います。2026年11月10日時点の掲載は令和7年度更新版です。削除年月が入った行や、有効なJGD2011座標がない行は検索対象から除外します。

- `updated_at` は検索対象のCSVにある作成・変更・削除年月の最新値です（`YYYY-MM`）。
- `dataset_title` と `catalog_updated_at` はカタログの情報です。`files` にCSVごとのURLとHTTPの更新日時、`checked_at` に取得・再確認した時刻を返します。
- 同じプロセス内では15分間キャッシュします。その後の最初の検索でカタログを読み直し、同じURLのCSVは、配信元が提供するETagやLast-Modifiedを使って再確認します。期限後の再確認に失敗した場合はエラーになります。

データには公表時点の情報が掲載されています。当日の設備や利用可否は施設・駅の案内を確認してください。

## 出典と利用条件

コードはMIT Licenseです。東京都福祉局の「車椅子使用者対応トイレのバリアフリー情報」を取得し、距離の計算と絞り込みを行っています。[東京都福祉局の案内](https://www.fukushi.metro.tokyo.lg.jp/kiban/machizukuri/bf_data)・[データカタログ](https://catalog.data.metro.tokyo.lg.jp/dataset/t000054d0000000342)・[データのライセンス（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.ja)

## 開発

```sh
uv sync --locked
uv run ruff check .
uv run ty check
uv run pytest
uv build
```
