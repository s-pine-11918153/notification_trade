import os
import requests
import yfinance as yf

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# データベースページ取得
url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
response = requests.post(url, headers=headers)
response.raise_for_status()

pages = response.json().get("results", [])

if not pages:
    print("ページが存在しません")
else:
    for page in pages:
        stock = page["properties"]["Stock"]["title"]
        stock_name = stock[0]["text"]["content"] if stock else "Unknown"

        ticker = page["properties"]["Ticker"]["rich_text"]
        ticker_code = ticker[0]["text"]["content"] if ticker else "Unknown"

        ticker_code = f"{ticker_code}.T" #Yahoo Financeでの日本株はティッカーコードの後に.Tをつける必要あり。

        condition = page["properties"]["condition"]["select"]
        condition_name = condition["name"] if condition else "None"

        deadline = page["properties"]["Deadline_Date"]["date"]
        deadline_date = deadline["start"] if deadline else "None"

        
        if not ticker_code:
            print(f"{stock_name} のティッカーコードが存在しません。スキップします。")
            continue
            
        print(f"Stock: {stock_name}, Ticker: {ticker_code}, Condition: {condition_name}, Deadline: {deadline_date}")

        # --- yfinance で株価取得 ---
        try:
            yf_stock = yf.Ticker(ticker_code)
            hist = yf_stock.history(period="1d")
            if hist.empty:
                close_price = None
                print(f"{ticker_code}: データが存在しません")
            else:
                close_price = hist["Close"].iloc[-1]
                print(f"{ticker_code}: 現在値 {close_price} 円")
        except Exception as e:
            print(f"{ticker_code}: 株価取得でエラー発生 - {e}")

        # Notionページ更新
        page_id = page["id"]
        
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        data = {
            "properties": {
                "Price": {"number": close_price} if close_price is not None else None,
                "URL": {"url": f"https://finance.yahoo.com/quote/{ticker_code}"}
            }
        }
        r = requests.patch(update_url, headers=headers, json=data)
        if r.status_code == 200:
            print(f"{stock_name} ({ticker_code}) 更新成功: 株価={close_price}")
        else:
            print(f"{stock_name} ({ticker_code}) 更新失敗: {r.status_code} {r.text}")
        
        # Discord に送信
        price_str = f"{close_price:,.0f} 円" if close_price is not None else "データなし"
        content = f"銘柄: {stock_name}\nティッカー: {ticker_code}\n株価: {price_str}"
        payload = {"content": content}
        
        try:
            r = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            print(f"Discord status: {r.status_code}")
            print(f"Discord response: {r.text}")
            r.raise_for_status()
        except Exception as e:
            print(f"Discord 送信エラー: {e}")
