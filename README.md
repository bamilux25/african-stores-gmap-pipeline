# african-stores-gmap-pipeline
Building a modern data engineering pipeline that extracts African store listings from Google Maps — collecting Place IDs via the Google Places API, scraping store details with Apify, loading into Azure SQL, and transforming with Databricks and Azure Data Factory. This project is built incrementally and documented step by step.

---

## ✅ Step 1 — Load UK City Reference Data

The first step is to get all UK cities (with their region and county) into the Azure SQL Database. This table acts as the geographic backbone of the pipeline — each city will later be joined with a search term (`"African store" + city`) to drive the Google Places API extraction, generating a Place ID for every city in the UK.

**What was done:**
- A CSV of 340 UK cities enriched with country, region, and county was prepared in Python
- The CSV was manually uploaded to Azure Blob Storage
- An Azure Data Factory Copy Pipeline moved the file from Blob Storage into the Azure SQL Database (`google.city_uk_region` table)
- The Azure SQL Database is connected to SSMS for local querying and development

**Script:** `01_setup_database.sql`

---

## ✅ Step 2 — Database Enrichment & Pipeline Tracking Setup

With the city reference data in place, the next step prepares the database for the extraction pipeline. This includes rebuilding the ethnic population table with the correct schema, adding a processing tracker column, and creating a summary table for market analysis.

**What was done:**
- Fixed the `Total_Population` column data type to `INT` on the ethnic population table
- Rebuilt `google.uk_city_ethinic_pop2` with a clean, correctly typed schema and repopulated it from the source table — this table holds city-level population data split by White, Black African, Asian, Other, and Total Non-White
- Added a `Processed BIT` column to `google.City_PlaceIDsAll` — defaulted to `0` — so the Python pipeline can track which Place IDs have already been sent to Apify and returned results
- Created `google.AfriStore_CountSummary` — an aggregated table that counts the number of African store Place IDs per city and joins with region and county, ready for Power BI reporting and market analysis

**Script:** `02_database_setup_and_enrichment.sql`

---

## ✅ Step 3 — Google Places API Extraction (Place IDs)

With the city table ready, a Python script loops through each city, builds the search term `"African store <city>"`, calls the Google Places Text Search API, and collects all returned Place IDs with pagination support.

**What was done:**
- Connected to Azure SQL and pulled all cities filtered by target region (Midlands)
- Built dynamic search terms per city — `"African store " + city_name`
- Called the Google Places API (`/v1/places:searchText`) with pagination via `nextPageToken` to retrieve up to 60 results per city
- Collected all Place IDs with their associated `city_id` and `city` name
- Deduplicated results and loaded into `google.City_PlaceIDsAll` in Azure SQL

**Script:** `02_google_placeid_extraction.py`

---

## ✅ Step 4 — Apify Place Details Scraping

With Place IDs loaded, a Python pipeline reads unprocessed IDs from Azure SQL in batches, sends them to the Apify Google Places Crawler, parses the returned business details, and writes the results back to Azure SQL.

**What was done:**
- Queried `google.City_PlaceIDsAll` for all records where `Processed = 0`
- Sent batches of up to 500 Place IDs to the Apify `compass/crawler-google-places` actor
- Parsed business details from each result including name, address, phone, website, category, and operational status
- Inserted parsed records into `google.Batch_PlaceDetails` in Azure SQL
- Updated `Processed = 1` on `google.City_PlaceIDsAll` using a composite key (`id + GooglePlaceID`) to prevent reprocessing
- Built in retry tracking — Place IDs that fail 3 or more times are excluded from future batches

**Script:** `03_apify_place_details_extraction.py`

---

> 📌 *This README will be updated at each stage of the pipeline build.*
