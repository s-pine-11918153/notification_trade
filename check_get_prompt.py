import os
import requests
import yfinance as yf

# --- 環境変数 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # GitHub Personal Access Token
REPO = os.getenv("REPO")  # ex) "user/repo-name"

WORKFLOW_NAME = "Stock Monitor"  # 保存するワークフロー名
MAX_RUNS_TO_KEEP = 1  # 💡最新3件のワークフローだけ残す

# --- Notion 共通ヘッダ ---
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# =========================================================
#             GitHub Actions 古いワークフロー自動削除
# =========================================================
def delete_old_workflows():
    if not GITHUB_TOKEN or not REPO:
        print("GitHub Token または REPO が設定されていません。ワークフロー削除はスキップします。")
        return

    print(f"\n=== 古い GitHub Actions ワークフロー削除開始（最新 {MAX_RUNS_TO_KEEP} 件だけ残す） ===")

    headers_github = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    # --- ワークフロー一覧取得 ---
    workflow_list_url = f"https://api.github.com/repos/{REPO}/actions/workflows"
    res = requests.get(workflow_list_url, headers=headers_github)
    res.raise_for_status()
    workflows = res.json().get("workflows", [])

    workflow_id = None
    for w in workflows:
        if w["name"] == WORKFLOW_NAME:
            workflow_id = w["id"]
            break

    if not workflow_id:
        print(f"ワークフロー '{WORKFLOW_NAME}' が見つかりません。")
        return

    print(f"対象ワークフロー: {WORKFLOW_NAME} (ID: {workflow_id})")

    # --- 実行履歴取得 ---
    runs_url = f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow_id}/runs?per_page=100"
    res = requests.get(runs_url, headers=headers_github)
    res.raise_for_status()
    runs = res.json().get("workflow_runs", [])

    total_runs = len(runs)
    print(f"現在の実行件数: {total_runs}")

    if total_runs <= MAX_RUNS_TO_KEEP:
        print("削除する必要はありません。")
        return

    # --- 最新 N 件だけ残す ---
    keep_runs = runs[:MAX_RUNS_TO_KEEP]
    delete_runs = runs[MAX_RUNS_TO_KEEP:]

    print(f"残すRun ID: {[run['id'] for run in keep_runs]}")
    print(f"削除対象Run数: {len(delete_runs)}")

    # --- 古い実行を削除 ---
    for run in delete_runs:
        run_id = run["id"]
        delete_url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}"
        r = requests.delete(delete_url, headers=headers_github)
        print(f"削除 Run {run_id}: {r.status_code}")

    print("=== 古いワークフロー削除完了 ===\n")


# =========================================================
#                        メイン処理
# =========================================================
def main():
    # --- Notion データベース取得 ---
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    response = requests.post(url, headers=NOTION_HEADERS)
    response.raise_for_status()
    pages = response.json().get("results", [])

    if not pages:
        print("ページが存在しません")
        return

    # --- 各ページ処理 ---
    for page in pages:
        page_id = page["id"]

        # --- 各プロパティ取得 ---
        country = page["properties"]["Country"]["select"]
        country_name = country["name"] if country else "None"

        stock = page["properties"]["Stock"]["title"]
        stock_name = stock[0]["text"]["content"] if stock else "Unknown"

        ticker = page["properties"]["Ticker"]["rich_text"]
        ticker_code_raw = ticker[0]["text"]["content"] if ticker else ""

        # --- 国によってティッカー加工 ---
        if country_name == "Japan":
            ticker_code = f"{ticker_code_raw}.T" if ticker_code_raw else None
        elif country_name == "US":
            ticker_code = ticker_code_raw if ticker_code_raw else None
        else:
            ticker_code = ticker_code_raw if ticker_code_raw else None

        condition = page["properties"]["condition"]["select"]
        condition_name = condition["name"] if condition else "None"

        deadline = page["properties"]["Deadline_Date"]["date"]
        deadline_date = deadline["start"] if deadline else "None"

        print(f"\n=== {stock_name} ===")
        print(f"Ticker: {ticker_code}, Condition: {condition_name}, Deadline: {deadline_date}")

        # --- ティッカーが無い場合スキップ ---
        if not ticker_code:
            print("ティッカーコードがありません。スキップ。")
            continue

        # --- yfinance で株価取得 ---
        try:
            yf_stock = yf.Ticker(ticker_code)
            yf_stock_name = yf_stock.info.get("longName")

            hist = yf_stock.history(period="1d")
            if hist.empty:
                close_price = None
                print("データなし")
            else:
                close_price = hist["Close"].iloc[-1]
                print(f"価格取得: {close_price}")

        except Exception as e:
            print(f"株価取得エラー: {e}")
            close_price = None
            yf_stock_name = stock_name

        # --- 名称が異なれば更新 ---
        if yf_stock_name and yf_stock_name != stock_name:
            stock_name = yf_stock_name

        # --- Notion ページ更新 ---
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        yf_URL = f"https://finance.yahoo.com/quote/{ticker_code}"

        update_data = {
            "properties": {
                "Stock": {
                    "title": [{"type": "text", "text": {"content": stock_name}}]
                },
                "Price": {"number": close_price} if close_price is not None else {"number": None},
                "URL": {"url": yf_URL}
            }
        }

        r = requests.patch(update_url, headers=NOTION_HEADERS, json=update_data)

        if r.status_code == 200:
            print(f"Notion 更新成功")
        else:
            print(f"Notion 更新失敗: {r.status_code} {r.text}")

        # --- 通知可否チェック ---
        notify = page["properties"].get("Allow_notification", {}).get("checkbox", False)
        if not notify:
            print("通知OFF → スキップ")
            continue

        # --- Discord 通知 ---
        price_str = (
            f"{close_price:,.0f} 円" if country_name == "Japan"
            else f"{close_price:,.2f} $" if country_name == "US"
            else f"{close_price}"
        )

        content = (
            f"銘柄: {stock_name}\n"
            f"ティッカー: {ticker_code}\n"
            f"株価: {price_str}\n"
            f"URL: {yf_URL}"
        )

        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
            print(f"Discord通知: {r.status_code}")
        except Exception as e:
            print(f"Discordエラー: {e}")

    # --- 最後にワークフロー古い履歴を削除 ---
    delete_old_workflows()


# =========================================================
#                       実行
# =========================================================
if __name__ == "__main__":
    main()
