# =============================================================================
# PROJECT      : African & Asian App — UK Market Analysis Pipeline
# SCRIPT       : 02_google_placeid_extraction.py
# DESCRIPTION  : Queries UK cities from Azure SQL, builds search terms
#                ("African store <city>"), calls the Google Places API to
#                retrieve Place IDs for each city, and loads the results
#                back into Azure SQL (google.City_PlaceIDsAll).
# AUTHOR       : A. Shittu
# CREATED      : 2026-05-22
# DEPENDENCIES : requests, pandas, sqlalchemy, pyodbc
# API          : Google Places API v1 (New) — Text Search
# DATABASE     : Azure SQL Database (Data_Scrapping_DB)
# =============================================================================

import time
import requests
import pandas as pd
import urllib.parse
from sqlalchemy import create_engine


# -----------------------------------------------------------------------------
# SECTION 1 | CONFIGURATION
# -----------------------------------------------------------------------------

# -- Google Places API --
API_KEY = 'xxxxx'                          # Replace before running
PLACES_URL = 'https://places.googleapis.com/v1/places:searchText'
HEADERS = {
    'X-Goog-Api-Key': API_KEY,
    'X-Goog-FieldMask': 'places.id,nextPageToken',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# -- Azure SQL Database --
SERVER   = 'elite247-prod.database.windows.net'
DATABASE = 'Data_Scrapping_DB'
USERNAME = 'a.shittu'
PASSWORD = 'XXXXXXX'                       # Replace before running

# -- Pipeline settings --
SEARCH_PREFIX  = 'African store'                       # Prepended to each city name
TARGET_REGION  = '%Midlands%'                          # SQL LIKE filter for region
TARGET_SCHEMA  = 'google'
TARGET_TABLE   = 'City_PlaceIDsAll'
PAGE_SIZE      = 20                                    # Google API max per page
MAX_RETRIES    = 3                                     # DB insert retry attempts


# -----------------------------------------------------------------------------
# SECTION 2 | DATABASE CONNECTION
# -----------------------------------------------------------------------------

def get_engine():
    """Creates a fresh SQLAlchemy engine with connection resilience settings."""
    connection_string = (
        f'DRIVER={{ODBC Driver 17 for SQL Server}};'
        f'SERVER={SERVER};DATABASE={DATABASE};'
        f'UID={USERNAME};PWD={PASSWORD};'
        f'TrustServerCertificate=yes'
    )
    quoted = urllib.parse.quote_plus(connection_string)
    return create_engine(
        f'mssql+pyodbc:///?odbc_connect={quoted}',
        use_setinputsizes=False,
        pool_pre_ping=True,     # validates connection before use
        pool_recycle=1800,      # recycles connection every 30 mins
        connect_args={"timeout": 30}
    )


# -----------------------------------------------------------------------------
# SECTION 3 | EXTRACT CITIES FROM SQL
# -----------------------------------------------------------------------------

def load_cities(engine) -> pd.DataFrame:
    """
    Pulls city reference data from Azure SQL filtered by region.
    Returns a DataFrame with city_id, city, and region columns.
    """
    sql = f"""
        SELECT
             city_id
            ,city
            ,region
            ,county
        FROM [Data_Scrapping_DB].[google].[uk_city_ethinic_pop2]
        WHERE region LIKE '{TARGET_REGION}'
    """
    print(f"Loading cities from SQL (region filter: {TARGET_REGION})...")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    df = df.fillna('')
    print(f"  {len(df)} cities loaded.\n")
    return df


# -----------------------------------------------------------------------------
# SECTION 4 | GOOGLE PLACES API — PLACE ID EXTRACTION
# -----------------------------------------------------------------------------

def fetch_place_ids(search_term: str) -> list:
    """
    Calls the Google Places Text Search API for a given search term.
    Handles pagination via nextPageToken and returns all Place IDs found.
    """
    all_ids       = []
    next_page_token = None

    while True:
        payload = {"textQuery": search_term, "pageSize": PAGE_SIZE}
        if next_page_token:
            payload["pageToken"] = next_page_token

        response = requests.post(PLACES_URL, headers=HEADERS, json=payload)
        parsed   = response.json()

        if parsed.get('places'):
            page_ids = [place['id'] for place in parsed['places']]
            all_ids.extend(page_ids)
            print(f"    Page fetched: {len(page_ids)} results | Running total: {len(all_ids)}")
        else:
            # No results or end of pages
            break

        next_page_token = parsed.get('nextPageToken')
        if not next_page_token:
            break

    return all_ids


def extract_all_place_ids(city_df: pd.DataFrame) -> pd.DataFrame:
    """
    Iterates over each city, builds the search term, calls the API,
    and accumulates all Place IDs into a single DataFrame.
    """
    all_results = []

    for _, row in city_df.iterrows():
        city_id    = row['city_id']
        city_name  = row['city'].strip()
        search_term = f"{SEARCH_PREFIX} {city_name}"

        print(f">>> [{city_id}] Searching: '{search_term}'")

        place_ids = fetch_place_ids(search_term)

        for place_id in place_ids:
            all_results.append({
                'city_id'      : city_id,
                'city'         : city_name,
                'search_term'  : search_term,
                'google_place_id': place_id
            })

        print(f"    Done — {len(place_ids)} Place IDs collected for {city_name}.\n")

    results_df = pd.DataFrame(all_results, columns=[
        'city_id', 'city', 'search_term', 'google_place_id'
    ])

    # Remove duplicates (same Place ID appearing in multiple pages)
    results_df = results_df.drop_duplicates(subset=['city_id', 'google_place_id'])

    return results_df


# -----------------------------------------------------------------------------
# SECTION 5 | LOAD RESULTS INTO AZURE SQL
# -----------------------------------------------------------------------------

def insert_with_retry(df: pd.DataFrame, retries: int = MAX_RETRIES):
    """
    Inserts the results DataFrame into Azure SQL.
    Creates a fresh engine on each retry to handle dropped connections.
    """
    for attempt in range(1, retries + 1):
        try:
            print(f"Inserting {len(df)} records into {TARGET_SCHEMA}.{TARGET_TABLE}...")
            fresh_engine = get_engine()
            with fresh_engine.begin() as conn:
                df.to_sql(
                    name=TARGET_TABLE,
                    con=conn,
                    schema=TARGET_SCHEMA,
                    if_exists='append',
                    index=False
                )
            print(f"  Insert successful. {len(df)} records loaded. ✅")
            return

        except Exception as e:
            print(f"  Attempt {attempt} failed: {e}")
            if attempt < retries:
                print(f"  Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("  All retries exhausted. Insert failed. ❌")
                raise


# -----------------------------------------------------------------------------
# SECTION 6 | MAIN PIPELINE EXECUTION
# -----------------------------------------------------------------------------

if __name__ == '__main__':

    print("=" * 60)
    print("  Google Places ID Extraction Pipeline")
    print("  African & Asian App — UK Market Analysis")
    print("=" * 60)

    # Step 1 — Connect and load cities
    engine  = get_engine()
    city_df = load_cities(engine)

    # Step 2 — Extract Place IDs from Google API
    results_df = extract_all_place_ids(city_df)

    # Step 3 — Summary before insert
    print("-" * 60)
    print(f"  Cities processed   : {results_df['city'].nunique()}")
    print(f"  Total Place IDs    : {len(results_df)}")
    print(f"  Duplicates removed : already deduplicated")
    print("-" * 60)
    print(results_df.head(10).to_string(index=False))
    print("-" * 60)

    # Step 4 — Insert into Azure SQL
    insert_with_retry(results_df)

    print("\nPipeline complete. ✅")
    print("=" * 60)
