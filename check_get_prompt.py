import os
import requests

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

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

        condition = page["properties"]["condition"]["select"]
        condition_name = condition["name"] if condition else "None"

        deadline = page["properties"]["Deadline_Date"]["date"]
        deadline_date = deadline["start"] if deadline else "None"

        print(f"Stock: {stock_name}, Ticker: {ticker_code}, Condition: {condition_name}, Deadline: {deadline_date}")
