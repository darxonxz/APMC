"""
Production-Ready Mandi Data Fetcher
Fetches agricultural market data from API with error handling, pagination, and logging
"""

import pandas as pd
import requests
import os
import logging
from datetime import datetime
import time
from typing import Optional

# ============================================================================
# CONFIGURATION & LOGGING SETUP
# ============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fetch_data.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Use environment variable for API key (security best practice)
API_KEY = os.getenv('MANDI_API_KEY', '579b464db66ec23bdd000001683b398a0bdd40066aefc6ace98749c7')
API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "market_data_master.csv")
BATCH_SIZE = 10000  # API limit per request
MAX_RETRIES = 3
TIMEOUT = 30

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def ensure_data_directory():
    """Create data directory if it doesn't exist"""
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Data directory ready: {DATA_DIR}")


def fetch_data_batch(offset: int, limit: int = BATCH_SIZE) -> Optional[pd.DataFrame]:
    """
    Fetch a batch of records from the API with retry logic
    
    Args:
        offset: Starting record number
        limit: Number of records to fetch (default: 10000)
    
    Returns:
        DataFrame or None if fetch fails
    """
    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": offset
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Fetching batch at offset {offset} (Attempt {attempt + 1}/{MAX_RETRIES})")
            response = requests.get(API_URL, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if records exist
            if 'records' not in data or len(data['records']) == 0:
                logger.info(f"No more records at offset {offset}")
                return None
            
            df = pd.DataFrame(data['records'])
            logger.info(f"Successfully fetched {len(df)} records from offset {offset}")
            return df
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed (Attempt {attempt + 1}): {str(e)}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed to fetch data after {MAX_RETRIES} attempts")
                return None
        except Exception as e:
            logger.error(f"Unexpected error during fetch: {str(e)}")
            return None


def fetch_all_data() -> Optional[pd.DataFrame]:
    """
    Fetch all available data using pagination
    
    Returns:
        Combined DataFrame or None if no data fetched
    """
    all_data = []
    offset = 0
    
    while True:
        batch_df = fetch_data_batch(offset)
        
        if batch_df is None or len(batch_df) == 0:
            logger.info("Pagination complete - no more records to fetch")
            break
        
        all_data.append(batch_df)
        offset += BATCH_SIZE
    
    if not all_data:
        logger.error("No data fetched from API")
        return None
    
    combined_df = pd.concat(all_data, ignore_index=True)
    logger.info(f"Total records fetched: {len(combined_df)}")
    return combined_df


def clean_and_validate_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and validate data quality
    
    Args:
        df: Raw DataFrame from API
    
    Returns:
        Cleaned DataFrame
    """
    original_rows = len(df)
    
    # Normalize column names (lowercase, strip whitespace)
    df.columns = df.columns.str.strip().str.lower()
    
    # Remove rows with all NaN values
    df.dropna(axis=0, how='all', inplace=True)
    
    # Check for required columns
    required_cols = ['state', 'district', 'market', 'commodity', 'variety', 
                     'grade', 'arrival_date', 'min_price', 'max_price', 'modal_price']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.warning(f"Missing columns: {missing_cols}")
    
    # Convert arrival_date to datetime
    if 'arrival_date' in df.columns:
        df['arrival_date'] = pd.to_datetime(df['arrival_date'], errors='coerce')
        nans_created = df['arrival_date'].isna().sum()
        if nans_created > 0:
            logger.warning(f"Date conversion created {nans_created} NaT values")
    
    # Convert price columns to numeric
    price_cols = ['min_price', 'max_price', 'modal_price']
    for col in price_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Validate price ranges (remove negative or zero prices)
    if 'min_price' in df.columns:
        invalid_prices = (df['min_price'] <= 0).sum() | (df['max_price'] < df['min_price']).sum()
        if invalid_prices > 0:
            logger.warning(f"Found {invalid_prices} invalid price ranges")
            df = df[(df['min_price'] > 0) & (df['max_price'] >= df['min_price'])]
    
    removed_rows = original_rows - len(df)
    if removed_rows > 0:
        logger.info(f"Removed {removed_rows} rows during cleaning")
    
    return df


def merge_with_existing_data(new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge new data with existing CSV, removing duplicates
    
    Args:
        new_df: New data fetched from API
    
    Returns:
        Combined DataFrame
    """
    ensure_data_directory()
    
    if os.path.exists(DATA_FILE):
        logger.info(f"Loading existing data from {DATA_FILE}")
        try:
            old_df = pd.read_csv(DATA_FILE)
            old_df['arrival_date'] = pd.to_datetime(old_df['arrival_date'], errors='coerce')
            logger.info(f"Existing records: {len(old_df)}")
            
            # Combine old and new data
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            logger.info(f"Combined records: {len(combined_df)}")
        except Exception as e:
            logger.error(f"Failed to load existing data: {str(e)}")
            combined_df = new_df
    else:
        logger.info("No existing data file - starting fresh")
        combined_df = new_df
    
    # Remove columns that are entirely empty
    combined_df = combined_df.dropna(axis=1, how='all')
    
    # Remove duplicates - keep the most recent record
    duplicate_cols = ['state', 'district', 'market', 'commodity', 'variety', 
                      'grade', 'arrival_date']
    before_dedup = len(combined_df)
    combined_df = combined_df.sort_values('arrival_date', ascending=False)
    combined_df = combined_df.drop_duplicates(subset=duplicate_cols, keep='first')
    
    removed_duplicates = before_dedup - len(combined_df)
    logger.info(f"Removed {removed_duplicates} duplicate records")
    
    return combined_df


def save_data(df: pd.DataFrame) -> bool:
    """
    Save data to CSV file
    
    Args:
        df: DataFrame to save
    
    Returns:
        True if successful, False otherwise
    """
    try:
        ensure_data_directory()
        df.to_csv(DATA_FILE, index=False)
        logger.info(f"Data saved successfully: {DATA_FILE}")
        logger.info(f"Total rows: {len(df)}, Total columns: {len(df.columns)}")
        return True
    except Exception as e:
        logger.error(f"Failed to save data: {str(e)}")
        return False


def main():
    """Main execution function"""
    logger.info("=" * 70)
    logger.info("MANDI DATA FETCH STARTED")
    logger.info("=" * 70)
    
    start_time = datetime.now()
    
    try:
        # Step 1: Fetch all data with pagination
        new_data = fetch_all_data()
        if new_data is None or len(new_data) == 0:
            logger.error("No data fetched. Aborting.")
            return False
        
        # Step 2: Clean and validate
        logger.info("Cleaning and validating data...")
        new_data = clean_and_validate_data(new_data)
        
        # Step 3: Merge with existing
        logger.info("Merging with existing data...")
        final_data = merge_with_existing_data(new_data)
        
        # Step 4: Save to CSV
        success = save_data(final_data)
        
        if success:
            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.info("=" * 70)
            logger.info(f"FETCH COMPLETED SUCCESSFULLY in {elapsed_time:.2f} seconds")
            logger.info(f"Final dataset: {len(final_data)} records, {len(final_data.columns)} columns")
            logger.info("=" * 70)
            return True
        else:
            logger.error("Failed to save data")
            return False
    
    except Exception as e:
        logger.error(f"Critical error in main execution: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
