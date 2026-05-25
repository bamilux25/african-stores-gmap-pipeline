# =============================================================================
# PROJECT      : African & Asian App — UK Market Analysis Pipeline
# SCRIPT       : 03_apify_place_details_extraction.py
# DESCRIPTION  : Reads unprocessed Google Place IDs from Azure SQL, sends them
#                in batches to the Apify Google Places Crawler, parses the
#                returned business details, loads results into Azure SQL, and
#                marks each Place ID as processed.
# AUTHOR       : A. Shittu
# CREATED      : 2025-09-15
# DEPENDENCIES : pandas, sqlalchemy, pyodbc, apify-client>=1.8.0
# ACTOR        : compass/crawler-google-places
# DATABASE     : Azure SQL Database (Data_Scrapping_DB)
# =============================================================================

import pandas as pd
import urllib
from sqlalchemy import create_engine, text
from apify_client import ApifyClient


# -----------------------------------------------------------------------------
# SECTION 1 | CONFIGURATION
# -----------------------------------------------------------------------------

# -- Azure SQL Database --
SERVER      = 'elite247-prod.database.windows.net'
DATABASE    = 'Data_Scrapping_DB'
USERNAME    = 'a.shittu'
PASSWORD    = 'YOUR_PASSWORD_HERE'                     # Replace before running

# -- Apify --
APIFY_TOKEN = 'YOUR_APIFY_TOKEN_HERE'                  # Replace before running

# -- Pipeline settings --
BATCH_SIZE  = 500                                      # Records per Apify run
MAX_RETRIES = 3                                        # Max attempts per Place ID


# -----------------------------------------------------------------------------
# SECTION 2 | HELPER FUNCTIONS
# -----------------------------------------------------------------------------

def TestNoneAndTruncate(inString, outLen):
    """Safely truncates a string to outLen characters. Returns None if input is None."""
    if inString:
        return inString[:outLen]
    return inString


def get_engine():
    """Creates a fresh SQLAlchemy engine with Azure SQL resilience settings."""
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
# SECTION 3 | INITIALISE CONNECTIONS
# -----------------------------------------------------------------------------

engine = get_engine()
client = ApifyClient(APIFY_TOKEN)

# In-memory tracker for Place IDs that repeatedly fail
attempt_tracker = {}


# -----------------------------------------------------------------------------
# SECTION 4 | MAIN PROCESSING LOOP
# -----------------------------------------------------------------------------

print("=" * 60)
print("  Apify Place Details Extraction Pipeline")
print("  African & Asian App — UK Market Analysis")
print("=" * 60)

while True:

    # -- Identify Place IDs that have failed too many times --
    bad_ids = [pid for pid, count in attempt_tracker.items() if count >= MAX_RETRIES]

    # -- Pull next unprocessed batch from SQL --
    query = """
        SELECT TOP (:BatchSize) id, GooglePlaceID
        FROM [google].[City_PlaceIDsAll]
        WHERE Processed <> 1
    """
    df = pd.read_sql(text(query), engine, params={"BatchSize": BATCH_SIZE})

    # -- Stop if no unprocessed records remain --
    if df.empty:
        print("No more records to process. Exiting loop.")
        break

    # -- Remove persistently failing Place IDs from this batch --
    if bad_ids:
        df = df[~df["GooglePlaceID"].isin(bad_ids)]

    if df.empty:
        print("Only failed IDs remain. Exiting loop.")
        break

    print(f"\nProcessing batch of {len(df)} records...")

    # -------------------------------------------------------------------------
    # SECTION 4a | BUILD BATCH & LOOKUP
    # -------------------------------------------------------------------------

    batch     = [(row["id"], row["GooglePlaceID"]) for _, row in df.iterrows()]
    place_ids = [pid for _, pid in batch]
    sf_lookup = {pid: sfid for sfid, pid in batch}   # maps PlaceID → row id

    # -------------------------------------------------------------------------
    # SECTION 4b | RUN APIFY ACTOR
    # -------------------------------------------------------------------------

    run_input = {
        "placeIds"                      : place_ids,
        "locationQuery"                 : "",
        "maxCrawledPlacesPerSearch"     : 5,
        "language"                      : "en",
        "maximumLeadsEnrichmentRecords" : 0,
        "maxRequestRetries"             : MAX_RETRIES
    }

    run = client.actor("compass/crawler-google-places").call(run_input=run_input)
    print(f"Apify Run ID: {run['id']}")

    # -------------------------------------------------------------------------
    # SECTION 4c | PARSE APIFY RESULTS
    # -------------------------------------------------------------------------

    parsed_data = []

    for item in client.dataset(run["defaultDatasetId"]).iterate_items():

        place_id = item.get("placeId", "")

        # Determine business operational status
        if item.get("permanentlyClosed", 0) == 1:
            business_status = "Permanently Closed"
        elif item.get("temporarilyClosed", 0) == 1:
            business_status = "Temporarily Closed"
        else:
            business_status = "Operational"

        parsed_data.append({
            "SF_id"               : sf_lookup.get(place_id),
            "GooglePlaceID"       : place_id,
            "DisplayName"         : TestNoneAndTruncate(item.get("title", ""),            255),
            "FullAddress"         : TestNoneAndTruncate(item.get("address", ""),          512),
            "FormattedStreet"     : TestNoneAndTruncate(item.get("street", ""),           255),
            "FormattedCity"       : TestNoneAndTruncate(item.get("city", ""),              40),
            "FormattedState"      : TestNoneAndTruncate(item.get("state", ""),             80),
            "FormattedPostalCode" : TestNoneAndTruncate(item.get("postalCode", ""),        20),
            "FormattedPhoneNo"    : TestNoneAndTruncate(item.get("phoneUnformatted", ""),  40),
            "Website"             : TestNoneAndTruncate(item.get("website", ""),          255),
            "BusinessCategory"    : TestNoneAndTruncate(item.get("categoryName", ""),      80),
            "BusinessStatus"      : business_status,
            "CountryCode"         : item.get("countryCode", "")
        })

    # -------------------------------------------------------------------------
    # SECTION 4d | INSERT RESULTS INTO AZURE SQL
    # -------------------------------------------------------------------------

    df_results = pd.DataFrame(parsed_data)

    if not df_results.empty:
        with engine.begin() as conn:
            df_results.to_sql(
                name      = "Batch_PlaceDetails",
                con       = conn,
                schema    = "google",
                if_exists = "append",
                index     = False
            )
        print(f"Inserted {len(df_results)} records into google.Batch_PlaceDetails.")

    # -------------------------------------------------------------------------
    # SECTION 4e | MARK BATCH AS PROCESSED (composite key: id + GooglePlaceID)
    # -------------------------------------------------------------------------

    if place_ids:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(text("""
                    UPDATE [google].[City_PlaceIDsAll]
                    SET    Processed = 1
                    WHERE  id            = :id
                    AND    GooglePlaceID = :place_id
                """), {"id": row["id"], "place_id": row["GooglePlaceID"]})
        print(f"Marked {len(place_ids)} records as Processed in google.City_PlaceIDsAll.")

    # -------------------------------------------------------------------------
    # SECTION 4f | TRACK FAILURES FOR EXCLUSION IN FUTURE BATCHES
    # -------------------------------------------------------------------------

    returned_ids = {p["GooglePlaceID"] for p in parsed_data}
    missing_ids  = set(place_ids) - returned_ids

    for pid in missing_ids:
        attempt_tracker[pid] = attempt_tracker.get(pid, 0) + 1
        if attempt_tracker[pid] >= MAX_RETRIES:
            print(f"Place ID {pid} failed {MAX_RETRIES} times — excluded from future batches.")


# -----------------------------------------------------------------------------
# SECTION 5 | COMPLETION
# -----------------------------------------------------------------------------

print("\nPipeline complete. ✅")
print("=" * 60)
