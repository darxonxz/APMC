import json
import logging
import os
import time
from typing import List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv


# Load .env if present
load_dotenv()

API_URL = (
    "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
)
API_KEY = os.getenv("MANDI_API_KEY", "")
FORMAT = "json"
BATCH_SIZE = 10000
MAX_RETRIES = 3
TIMEOUT = 30
OUTPUT_PATH = os.path.join("data", "market_data_master.csv")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def fetch_batch(offset: int) -> Optional[pd.DataFrame]:
    params = {
        "api-key": API_KEY,
        "format": FORMAT,
        "limit": BATCH_SIZE,
        "offset": offset,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Fetching batch at offset {offset} (attempt {attempt})")
            resp = requests.get(API_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            if "records" not in data:
                logger.error("No 'records' key in response")
                return None

            records = data["records"]
            if not records:
                logger.info("Empty records list returned.")
                return pd.DataFrame()

            df = pd.DataFrame(records)
            return df

        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error: {e}")
            if attempt == MAX_RETRIES:
                logger.error("Max retries reached, aborting.")
                return None
            time.sleep(2**attempt)
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response.")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return None

    return None


def fetch_all() -> pd.DataFrame:
    if not API_KEY:
        raise RuntimeError("MANDI_API_KEY is not set in environment.")

    all_dfs: List[pd.DataFrame] = []
    offset = 0

    while True:
        batch_df = fetch_batch(offset)
        if batch_df is None:
            # Hard error
            break

        if batch_df.empty:
            # No more data
            break

        all_dfs.append(batch_df)
        logger.info(f"Fetched {len(batch_df)} records at offset {offset}")
        offset += BATCH_SIZE

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Total fetched records: {len(combined)}")
    return combined


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    # Rename to simpler snake_case
    col_map = {
        "state": "state",
        "district": "district",
        "market": "market",
        "commodity": "commodity",
        "variety": "variety",
        "grade": "grade",
        "arrival_date": "arrival_date",
        "min_price": "min_price",
        "max_price": "max_price",
        "modal_price": "modal_price",
    }

    # Try to map also from original API names
    for col in list(df.columns):
        lc = col.lower()
        if lc in col_map and col_map[lc] not in df.columns:
            df.rename(columns={col: col_map[lc]}, inplace=True)

    # Strip strings
    for col in ["state", "district", "market", "commodity", "variety", "grade"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Dates
    if "arrival_date" in df.columns:
        df["arrival_date"] = pd.to_datetime(df["arrival_date"], errors="coerce")

    # Prices
    for col in ["min_price", "max_price", "modal_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Basic validation
    invalid_prices = 0
    if {"min_price", "max_price"}.issubset(df.columns):
        invalid_prices = ((df["min_price"] <= 0) | (df["max_price"] < df["min_price"])).sum()
        df = df[(df["min_price"] > 0) & (df["max_price"] >= df["min_price"])]

    if invalid_prices > 0:
        logger.warning(f"Removed {invalid_prices} rows with invalid price ranges.")

    if "arrival_date" in df.columns:
        before = len(df)
        df = df.dropna(subset=["arrival_date"])
        dropped = before - len(df)
        if dropped > 0:
            logger.warning(f"Dropped {dropped} rows with invalid arrival_date.")

    logger.info(f"Cleaned dataset rows: {len(df)}")
    return df


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    try:
        df_raw = fetch_all()
        if df_raw.empty:
            logger.error("No data fetched; output file will not be updated.")
            return

        df_clean = clean_data(df_raw)
        df_clean.to_csv(OUTPUT_PATH, index=False)
        logger.info(f"Saved cleaned data to {OUTPUT_PATH} ({len(df_clean)} rows)")

    except Exception as e:
        logger.exception(f"Fatal error in fetch script: {e}")


if __name__ == "__main__":
    main()
