# african-stores-gmap-pipeline

Building a modern data engineering pipeline that extracts African store listings from Google Maps — collecting Place IDs via the free Places API, scraping store details with Python Selenium, loading into SQL Server, and transforming with Databricks and Azure Data Factory. This project is built incrementally and documented step by step.

---

## ✅ Step 1 — Load UK City Reference Data

The first step is to get all UK cities (with their region and county) into the Azure SQL Database. This table acts as the geographic backbone of the pipeline — each city will later be joined with a search term (`"African store" + city`) to drive the Google Places API extraction, generating a Place ID for every city in the UK.

**What was done:**
- A CSV of 340 UK cities enriched with country, region, and county was prepared in Python
- The CSV was manually uploaded to Azure Blob Storage
- An Azure Data Factory Copy Pipeline moved the file from Blob Storage into the Azure SQL Database (`google.city_uk_region` table)
- The Azure SQL Database is connected to SSMS for local querying and development

**Next:** The Python script will loop through each city in this table, build the search term, call the Google Places API, and load the returned Place IDs back into the database.

---

> 📌 *This README will be updated at each stage of the pipeline build.*
