import pandas as pd
import requests
import os

API_KEY = os.getenv("MANDI_API_KEY", "")  # 👈 from GitHub Secrets

if not API_KEY:
    raise RuntimeError("DATA_GOV_API_KEY not set")

url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
LIMIT = 10000
offset = 0
all_records = []

headers = {
    "User-Agent": "mandi-data-pipeline/1.0"
}

while True:
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": LIMIT,
        "offset": offset
    }

    r = requests.get(url, params=params, headers=headers, timeout=30)

    if r.status_code == 403:
        raise RuntimeError("403 Forbidden – API key invalid or quota exceeded")

    r.raise_for_status()

    data = r.json().get("records", [])
    if not data:
        break

    all_records.extend(data)
    offset += LIMIT

print("Fetched records:", len(all_records))

new_df = pd.DataFrame(all_records)
new_df.columns = new_df.columns.str.strip().str.lower()
new_df["arrival_date"] = pd.to_datetime(new_df["arrival_date"], errors="coerce")

DATA_FILE = "data/market_data_master.csv"
os.makedirs("data", exist_ok=True)

if os.path.exists(DATA_FILE):
    old_df = pd.read_csv(DATA_FILE)
    df = pd.concat([old_df, new_df], ignore_index=True)
else:
    df = new_df

df.drop_duplicates(
    subset=["state", "district", "market", "commodity", "variety", "arrival_date"],
    keep="last",
    inplace=True
)

df.to_csv(DATA_FILE, index=False)

print("Final rows:", len(df))
