import os
import requests
from datetime import datetime
import yfinance as yf

# --- 環境変数 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- Notion headers ---
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# --- データベースからページ取得 ---
def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()["results"]

# --- 株価取得 ---
def get_stock_price(ticker):
    stock = yf.Ticker(ticker)
    price = stock.history(period="1d")["Close"][-1]
    return price

# --- Discord通知 ---
def send_discord_message(content):
    payload = {"content": content}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    response.raise_for_status()

# --- メイン処理 ---
def main():
    pages = get_notion_pages()
    today = datetime.today().date()

    for page in pages:
        # タイトル（銘柄名）
        title_list = page["properties"]["Stock"]["title"]
        stock_name = title_list[0]["text"]["content"] if title_list else "Unknown"

        # ティッカーコード
        ticker_list = page["properties"]["Ticker"]["rich_text"]
        ticker = ticker_list[0]["text"]["content"] if ticker_list else None
        if not ticker:
            continue

        # 条件
        condition_select = page["properties"]["condition"]["select"]
        condition = condition_select["name"] if condition_select else None

        # 通知期限
        deadline = page["properties"]["Deadline_Date"]["date"]
        if deadline and deadline["start"]:
            deadline_date = datetime.fromisoformat(deadline["start"]).date()
            if today > deadline_date:
                continue  # 期限切れ

        # 株価取得
        price = get_stock_price(ticker)

        # 条件判定（例: price > 3000）
        if condition == "price > 3000" and price > 3000:
            message = f"{stock_name}({ticker}) 現在価格: {price} 条件達成!"
            send_discord_message(message)
            print(message)

if __name__ == "__main__":
    main()
