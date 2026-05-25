/* =============================================================================
   PROJECT      : African & Asian App — UK Market Analysis Pipeline
   SCRIPT       : 02_database_setup_and_enrichment.sql
   DESCRIPTION  : Restructures the UK city ethnic population table, adds a
                  processing tracker column to the Place IDs table, and creates
                  a summary table of African store counts per city.
   AUTHOR       : A. Shittu
   CREATED      : 2026-05-22
   DATABASE     : Azure SQL Database (Data_Scrapping_DB)
   SCHEMA       : google
   ============================================================================= */


/* -----------------------------------------------------------------------------
   SECTION 1 | FIX COLUMN DATA TYPE
   Purpose : Ensure Total_Population is stored as INT not string
   ----------------------------------------------------------------------------- */

ALTER TABLE google.[uk_city_ethinic_pop]
ALTER COLUMN Total_Population INT;
GO


/* -----------------------------------------------------------------------------
   SECTION 2 | VALIDATION QUERY — MIDLANDS SNAPSHOT
   Purpose : Sanity check — view Midlands cities ordered by Black African pop
   ----------------------------------------------------------------------------- */

SELECT *
FROM [google].[uk_city_ethinic_pop]
WHERE  region LIKE '%Midlands%'
ORDER BY [Black_African] DESC;
GO


/* -----------------------------------------------------------------------------
   SECTION 3 | REBUILD CLEAN ETHNIC POPULATION TABLE
   Purpose : Drop and recreate uk_city_ethinic_pop2 with correct schema,
             then repopulate from the source table.
   Note    : Percentage columns stored as NVARCHAR to preserve formatted values
             e.g. "14.3%" — convert to FLOAT if numeric operations needed later.
   ----------------------------------------------------------------------------- */

IF OBJECT_ID('Data_Scrapping_DB.google.uk_city_ethinic_pop2', 'U') IS NOT NULL
BEGIN
    DROP TABLE [google].[uk_city_ethinic_pop2];
    PRINT 'Dropped existing table: google.uk_city_ethinic_pop2';
END
GO

CREATE TABLE [google].[uk_city_ethinic_pop2] (
     [city_id]           INT              NULL
    ,[City]              NVARCHAR(255)    NULL
    ,[Country]           NVARCHAR(100)    NULL
    ,[Region]            NVARCHAR(100)    NULL
    ,[County]            NVARCHAR(100)    NULL
    ,[Total_Population]  INT              NULL
    ,[White]             INT              NULL
    ,[% white]           NVARCHAR(20)     NULL
    ,[Black_African]     INT              NULL
    ,[%Black African]    NVARCHAR(20)     NULL
    ,[Asian]             INT              NULL
    ,[%Asian]            NVARCHAR(20)     NULL
    ,[Other_Ethnicity]   INT              NULL
    ,[% other_Ethinic]   NVARCHAR(20)     NULL
    ,[Total_NonWhite]    INT              NULL
    ,[% non_white]       NVARCHAR(20)     NULL
) ON [PRIMARY];
GO

PRINT 'Created table: google.uk_city_ethinic_pop2';

-- Populate from source table
INSERT INTO [google].[uk_city_ethinic_pop2]
SELECT *
FROM   [google].[uk_city_ethnic_pop];

PRINT 'Data loaded into google.uk_city_ethinic_pop2.';
GO


/* -----------------------------------------------------------------------------
   SECTION 4 | ADD PROCESSING TRACKER TO PLACE IDs TABLE
   Purpose : Adds a Processed BIT column to track which Place IDs have been
             sent to Apify and returned results. Default = 0 (unprocessed).
             The Python pipeline updates this to 1 after each successful batch.
   ----------------------------------------------------------------------------- */

ALTER TABLE [google].[City_PlaceIDsAll]
ADD Processed BIT DEFAULT 0;
GO

-- Initialise all existing rows to unprocessed
UPDATE [google].[City_PlaceIDsAll]
SET    Processed = 0;

PRINT 'Processed column added and initialised on google.City_PlaceIDsAll.';
GO


/* -----------------------------------------------------------------------------
   SECTION 5 | VALIDATION — CONFIRM TRACKER COLUMN
   ----------------------------------------------------------------------------- */

SELECT TOP 20 *
FROM [google].[City_PlaceIDsAll]
ORDER BY id;
GO


/* -----------------------------------------------------------------------------
   SECTION 6 | CREATE AFRICAN STORE COUNT SUMMARY TABLE
   Purpose : Aggregates total African store Place IDs per city and joins with
             region/county from the ethnic population table.
             Used for market analysis and Power BI reporting.
   ----------------------------------------------------------------------------- */

IF OBJECT_ID('Data_Scrapping_DB.google.AfriStore_CountSummary', 'U') IS NOT NULL
BEGIN
    DROP TABLE [google].[AfriStore_CountSummary];
    PRINT 'Dropped existing table: google.AfriStore_CountSummary';
END
GO

WITH CTE_StoreCount AS (
    SELECT
         id
        ,City
        ,SearchTerm
        ,COUNT(*) AS AfriStore_Count
    FROM [google].[City_PlaceIDsAll]
    GROUP BY
         id
        ,City
        ,SearchTerm
)
SELECT
     x.id
    ,x.City
    ,y.Region
    ,y.County
    ,x.SearchTerm
    ,x.AfriStore_Count
INTO [google].[AfriStore_CountSummary]
FROM       CTE_StoreCount                  x
INNER JOIN [google].[uk_city_ethinic_pop2] y
        ON x.id = y.city_id;

PRINT 'Summary table created: google.AfriStore_CountSummary';
GO


/* -----------------------------------------------------------------------------
   SECTION 7 | VALIDATION — REVIEW SUMMARY OUTPUT
   ----------------------------------------------------------------------------- */

SELECT *
FROM  [google].[AfriStore_CountSummary]
ORDER BY AfriStore_Count DESC;
GO


/* =============================================================================
   END OF SCRIPT
   ============================================================================= */
