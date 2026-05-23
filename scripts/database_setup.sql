
/* =============================================================================
   PROJECT      : UK Business Lead Generation (Google Places API)
   SCRIPT       : 01_setup_database.sql
   DESCRIPTION  : Creates the Data_Scrapping_DB database, schemas, staging and
                  production tables, and loads UK city/region reference data
                  from a local CSV export.
   AUTHOR       : Ahmed Shittu
   CREATED      : 2026-05-22
   DATABASE     : SQL Server (T-SQL)
   ARCHITECTURE : Medallion-style schema separation (google schema = raw/source)
   ============================================================================= */


/* -----------------------------------------------------------------------------
   SECTION 1 | DATABASE SETUP
   ----------------------------------------------------------------------------- */

USE master;
GO

-- Drop and recreate database (clean slate for development)
IF EXISTS (SELECT 1 FROM sys.databases WHERE name = 'Data_Scrapping_DB')
BEGIN
    PRINT 'Dropping existing database: Data_Scrapping_DB';
    DROP DATABASE Data_Scrapping_DB;
END

PRINT 'Creating database: Data_Scrapping_DB';
CREATE DATABASE Data_Scrapping_DB;
GO

-- Switch context to new database
USE Data_Scrapping_DB;
GO


/* -----------------------------------------------------------------------------
   SECTION 2 | SCHEMA SETUP
   Note: Medallion Architecture pattern - google schema holds source/raw data
   ----------------------------------------------------------------------------- */

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'google')
BEGIN
    EXEC('CREATE SCHEMA google');
    PRINT 'Schema created: google';
END
GO


/* -----------------------------------------------------------------------------
   SECTION 3 | STAGING TABLE
   Purpose : Temporary landing zone for BULK INSERT from CSV
   ----------------------------------------------------------------------------- */

IF OBJECT_ID('google.city_uk_region_stage', 'U') IS NOT NULL
BEGIN
    DROP TABLE google.city_uk_region_stage;
    PRINT 'Dropped existing staging table: google.city_uk_region_stage';
END

CREATE TABLE google.city_uk_region_stage (
     city        NVARCHAR(100)
    ,country     NVARCHAR(100)
    ,region      NVARCHAR(100)
    ,county      NVARCHAR(100)
);
GO

PRINT 'Created staging table: google.city_uk_region_stage';


/* -----------------------------------------------------------------------------
   SECTION 4 | PRODUCTION TABLE
   Purpose : Clean, keyed reference table for city/region lookups
   ----------------------------------------------------------------------------- */

IF OBJECT_ID('google.city_uk_region', 'U') IS NOT NULL
BEGIN
    DROP TABLE google.city_uk_region;
    PRINT 'Dropped existing production table: google.city_uk_region';
END

CREATE TABLE google.city_uk_region (
     city_id     INT           IDENTITY(1,1)   NOT NULL
    ,city        NVARCHAR(100)                 NOT NULL
    ,country     NVARCHAR(100)                 NOT NULL
    ,region      NVARCHAR(100)                 NOT NULL
    ,county      NVARCHAR(100)                 NOT NULL

    ,CONSTRAINT PK_city_uk_region PRIMARY KEY CLUSTERED (city_id)
);
GO

PRINT 'Created production table: google.city_uk_region';


/* -----------------------------------------------------------------------------
   SECTION 5 | BULK LOAD — CSV INTO STAGING
   Note : Update the file path below to match your local environment.
          For team use, consider placing the CSV in a shared/network path
          or loading via ADF / COPY INTO for cloud deployments.
   ----------------------------------------------------------------------------- */

PRINT 'Starting BULK INSERT into staging table...';

BULK INSERT google.city_uk_region_stage
FROM 'C:\Users\PC Deals\Downloads\uk_cities_enriched.csv'
WITH (
     FORMAT          = 'CSV'
    ,FIELDTERMINATOR = ','
    ,ROWTERMINATOR   = '\n'
    ,FIRSTROW        = 2        -- Skip header row
    ,TABLOCK                    -- Table-level lock for faster load
);
GO

PRINT 'BULK INSERT complete.';


/* -----------------------------------------------------------------------------
   SECTION 6 | LOAD STAGING → PRODUCTION
   ----------------------------------------------------------------------------- */

PRINT 'Loading production table from staging...';

INSERT INTO google.city_uk_region
    (city, country, region, county)
SELECT
     city
    ,country
    ,region
    ,county
FROM google.city_uk_region_stage
WHERE city    IS NOT NULL
  AND country IS NOT NULL;   -- Basic data quality guard
GO

PRINT 'Production table loaded successfully.';


/* -----------------------------------------------------------------------------
   SECTION 7 | VALIDATION QUERIES
   Purpose : Quick sanity checks after load — review output before proceeding
   ----------------------------------------------------------------------------- */

-- Row count check
SELECT
     'google.city_uk_region_stage'   AS table_name
    ,COUNT(*)                         AS row_count
FROM google.city_uk_region_stage

UNION ALL

SELECT
     'google.city_uk_region'
    ,COUNT(*)
FROM google.city_uk_region;

-- Distribution by country
SELECT
     country
    ,region
    ,COUNT(*) AS city_count
FROM google.city_uk_region
GROUP BY
     country
    ,region
ORDER BY
     country
    ,city_count DESC;

-- Sample records
SELECT TOP 10 *
FROM google.city_uk_region
ORDER BY city_id;
GO


/* =============================================================================
   END OF SCRIPT
   ============================================================================= */
