# -*- coding: utf-8 -*-
"""
Created on Fri May 22 15:57:57 2026

@author: PC Deals
"""

API_KEY='Your API_KEY'

import requests
import json
import pandas as pd
import urllib
from sqlalchemy import create_engine, text


# Google Places API endpoint
url = 'https://places.googleapis.com/v1/places:searchText'
headers = {
    'X-Goog-Api-Key': API_KEY,
    'X-Goog-FieldMask': 'places.id,nextPageToken',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}


# SQL setup credentials
server   = 'elite247-prod.database.windows.net'
database = 'Data_Scrapping_DB'
SQLUserName = 'a.shittu'
SQLPass  = 'XXXXXXXXX'

quoted = urllib.parse.quote_plus(
    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};'
    f'UID={SQLUserName};PWD={SQLPass};TrustServerCertificate=yes'
)
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={quoted}', use_setinputsizes=False)

# --- Step 1: Extract cities from SQL ---
with engine.connect() as conn:
    sql = """
        SELECT city_id ,city, region, county, total_population,
               black_african, [%black african], asian, [%asian]
        FROM [Data_Scrapping_DB].[google].[uk_city_ethinic_pop2]
        WHERE region LIKE '%Midlands%'
    """
    city_df = pd.read_sql(sql, conn)

city_df = city_df.fillna('')

# --- Step 2: Loop through cities and collect Place IDs ---
all_results = []

for index, row in city_df.iterrows():
    city_name  = row['city'].strip()
    city_id = row['city_id']
    searchTerm = "African store " + city_name

    allIDs        = []
    nextPageToken = None

    print(f"\n>>> Searching: {searchTerm}")

    while True:
        payload = {"textQuery": searchTerm, "pageSize": 20}

        if nextPageToken:
            payload["pageToken"] = nextPageToken

        response       = requests.post(url, headers=headers, json=payload)
        parsedResponse = response.json()

        if parsedResponse.get('places'):
            theseIDs = [place['id'] for place in parsedResponse['places']]
            allIDs.extend(theseIDs)
        else:
            break

        nextPageToken = parsedResponse.get('nextPageToken')
        if not nextPageToken:
            break

    for place_id in allIDs:
        all_results.append({
            'City'         : city_name,
            'City_id'      : city_id,
            'searchTerm'   : searchTerm,
            'GooglePlaceID': place_id
        })

    print(f"  {city_name}: {len(allIDs)} Place IDs found")

# --- Step 3: Final DataFrame ---
results_df = pd.DataFrame(all_results, columns=['City_id','searchTerm','City', 'GooglePlaceID'])

 # --- Step 4: Clean final columns ---
Final_result = results_df[[
        "City_id","City", "searchTerm", "GooglePlaceID"
    ]].rename(columns={"City_id": "id"}).drop_duplicates()

# --- Step 5: Insert into SQL ---
with engine.begin() as conn:  # begin auto-commits
        Final_result.to_sql(
            "City_PlaceIDsAll", 
            con=conn, 
            schema="google", 
            if_exists="append",  # change to "replace" if overwriting
            index=False
        )

print(f"Inserted {len(Final_result)} records into City_PlaceIDsAll ✅")

