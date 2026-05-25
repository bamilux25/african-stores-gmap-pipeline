# -*- coding: utf-8 -*-
"""
Created on Thu Sep 11 17:47:42 2025

@author: a.shittu
"""


from logging.handlers import QueueHandler, QueueListener
from tqdm import tqdm
from math import ceil
import pandas as pd
import logging
import multiprocessing
import time
import re
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process

class GoogleMapsScraper:
    def __init__(self, driver_path, debug=False):
        """
        Initializes the GoogleMapsScraper class.
        """
        logger = logging.getLogger(f"scraper_{multiprocessing.current_process().pid}")
        logger.debug(f"Initializing ChromeDriver, debug={debug}")
        
        self.service = Service(driver_path)
        self.service.start()
        
        chrome_options = Options()
        if not debug:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.page_load_strategy = "eager"
        
        self.driver = webdriver.Remote(self.service.service_url, options=chrome_options)
        self.cookie_handled = False

    def click_on_cookie_agreement(self):
        if self.cookie_handled:
            return
        logger = logging.getLogger(f"scraper_{multiprocessing.current_process().pid}")
        try:
            WebDriverWait(self.driver, 3).until(
                EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe[src*='consent']"))
            )
        except TimeoutException:
            logger.debug("No consent iframe found")
        try:
            reject_button = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.XPATH,
                    '//button[.//div[text()="Reject all"] or .//span[text()="Reject all"] or .//span[text()="Decline all"]]'))
            )
            reject_button.click()
            time.sleep(1)
            logger.debug("Clicked cookie reject button")
        except TimeoutException:
            logger.debug("No cookie banner appeared")
        finally:
            self.driver.switch_to.default_content()
            self.cookie_handled = True

    def open_place_by_id(self, place_id):
        """Navigate directly to a Google Maps place using its Place ID"""
        logger = logging.getLogger(f"scraper_{multiprocessing.current_process().pid}")
        try:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            logger.debug(f"Opening Place ID URL: {url}")
            self.driver.get(url)
            self.click_on_cookie_agreement()
        except Exception as e:
            logger.error(f"Failed to open place by ID {place_id}: {e}")
            raise

    def extract_company_details(self):
        """Extract name, address, website, business type, and phone number from the loaded place page."""
        logger = logging.getLogger(f"scraper_{multiprocessing.current_process().pid}")
        name, address, website, business_type, phone_number = "N/A", "N/A", "None", "None", "N/A"
        try:
            name_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, '//h1[@class="DUwDvf lfPIob"]'))
            )
            name = name_element.text.strip()
            logger.debug(f"Extracted name: {name}")
        except Exception as e:
            logger.warning(f"Failed to extract name via Selenium: {str(e)}")
            name = "N/A"
            try:
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                h1_tags = soup.find_all('h1')
                for h1 in h1_tags:
                    text = h1.get_text(strip=True)
                    if 3 < len(text) < 150 and not any(keyword in text.lower() for keyword in ['nearby', 'review', 'address', 'website']):
                        name = text
                        logger.debug(f"Extracted name via BeautifulSoup: {name}")
                        break
            except Exception as soup_e:
                logger.warning(f"BeautifulSoup fallback failed for name: {soup_e}")
        address_xpaths = [
            '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]',
            '//div[contains(@aria-label, "Address") or contains(text(), "Address")]'
        ]
        address_pattern = re.compile(
            r'\d+\s+\w+.*,\s*\w+|'
            r'\b(st|rd|ave|blvd|ln|way|dr|ct|pl)\b|'
            r'[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|'
            r'\d{5}(-\d{4})?'
            , re.IGNORECASE
        )
        for xpath in address_xpaths:
            try:
                address_element = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, xpath))
                )
                address = address_element.text.strip()
                if address_pattern.search(address):
                    logger.debug(f"Address found using XPath: {xpath}")
                    break
                else:
                    logger.debug(f"Text from XPath {xpath} does not appear to be a valid address: {address}")
                    address = "N/A"
            except TimeoutException:
                logger.debug(f"Timeout on XPath {xpath}")
                continue
            except Exception as e:
                logger.warning(f"Error with XPath {xpath}: {str(e)}")
                continue
        if address == "N/A":
            try:
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                for div in soup.find_all('div', text=address_pattern):
                    txt = div.get_text(strip=True)
                    if any(bad in txt.lower() for bad in [
                        "nearby hotels", "restaurants", "things to do", "coffee", "parking", "collapse side panel",
                        "check availability", "book now", "reserve", "deals", "book a room"
                    ]):
                        continue
                    if 10 < len(txt) < 200 and address_pattern.search(txt):
                        address = txt
                        logger.debug("Address found using BeautifulSoup fallback")
                        break
            except Exception as soup_e:
                logger.warning(f"Soup fallback failed: {str(soup_e)}")
        try:
            website_element = WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((
                    By.XPATH, 
                    '//div[contains(@class, "rogA2c") and contains(@class, "ITvuef")]//div[contains(@class, "Io6YTe") and contains(text(), ".")]'
                ))
            )
            website = website_element.text.strip()
            logger.debug(f"Extracted website: {website}")
        except (TimeoutException, NoSuchElementException):
            try:
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                parent_div = soup.find('div', class_=lambda x: x and 'rogA2c' in x and 'ITvuef' in x)
                if parent_div:
                    website_element = parent_div.find(
                        'div', 
                        class_='Io6YTe', 
                        string=lambda text: text and '.' in text and any(tld in text for tld in ['.com', '.co', '.org', '.uk'])
                    )
                    website = website_element.text.strip() if website_element else "None"
                    logger.debug(f"Extracted website via BeautifulSoup: {website}")
                else:
                    website = "None"
            except Exception:
                website = "None"
        try:
            business_type_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((
                    By.XPATH,
                    '//button[contains(@class,"DkEaL")]'
                ))
            )
            business_type = business_type_element.text.strip()
            logger.debug(f"Extracted business type: {business_type}")
        except Exception:
            try:
                business_type_element = WebDriverWait(self.driver, 5).until(
                    EC.visibility_of_element_located((
                        By.XPATH,
                        '(//div[contains(@class, "LBgpqf")]//span/span[string-length(normalize-space()) > 0])[5]'
                    ))
                )
                business_type = business_type_element.text.strip()
                logger.debug(f"Extracted business type via fallback: {business_type}")
            except Exception:
                business_type = "None"
        try:
            phone_number_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((
                    By.XPATH,
                    '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                ))
            )
            phone_number = phone_number_element.text.strip()
            logger.debug(f"Extracted phone number: {phone_number}")
        except (TimeoutException, NoSuchElementException):
            try:
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                parent_button = soup.find('button', attrs={'data-item-id': lambda x: x and 'phone:tel:' in x})
                if parent_button:
                    phone_number_element = parent_button.find(
                        'div', 
                        class_='fontBodyMedium', 
                        string=lambda text: text and re.match(r'^[0+][0-9\s+-]*$|[0-9]+[\s+-][0-9]', text.strip())
                    )
                    phone_number = phone_number_element.text.strip() if phone_number_element else "N/A"
                    logger.debug(f"Extracted phone number via BeautifulSoup: {phone_number}")
                else:
                    phone_number = "N/A"
            except Exception:
                phone_number = "N/A"
        return name, address, website, business_type, phone_number

    def scrap_company_details_by_place_id(self, place_id):
        """
        Directly scrape details from Google Maps using a Place ID.
        Returns: (name, address, website, business_type, phone_number)
        """
        logger = logging.getLogger(f"scraper_{multiprocessing.current_process().pid}")
        try:
            self.open_place_by_id(place_id)
            WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, '//h1[@class="DUwDvf lfPIob"]'))
            )
            return self.extract_company_details()
        except Exception as e:
            logger.error(f"Error scraping Place ID {place_id}: {e}")
            return None, None, None, None, None

    def close(self):
        """Close the driver and service."""
        try:
            self.driver.quit()
            self.service.stop()
        except Exception:
            pass


# --- Unchanged: Address Parsing Function ---
postcode_regex = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{1,2}\b"
region_keywords = ["shire", "sex", "midland"]
invalid_city_state_keywords = ["road", "street", "avenue", "lane", "close", "way", "place",
                              "boulevard", "terrace", "court", "drive", "crescent", "highway"]

def is_state(segment):
    segment_lower = segment.lower()
    return any(k in segment_lower for k in region_keywords)

def is_invalid_city_state(segment):
    return (
        segment.strip().isdigit() or
        any(k in segment.lower() for k in invalid_city_state_keywords)
    )

def parse_address(full_address):
    if not isinstance(full_address, str):
        return pd.Series(["", None, None, None])
    postcode_match = re.search(postcode_regex, full_address, re.IGNORECASE)
    postcode = postcode_match.group(0).upper() if postcode_match else None
    address_wo_postcode = re.sub(postcode_regex, "", full_address, flags=re.IGNORECASE).strip(", ")
    parts = [p.strip() for p in address_wo_postcode.split(",") if p.strip()]
    address = city = state = None
    if not parts:
        return pd.Series(["", None, None, postcode])
    if len(parts) == 1:
        address = parts[0]
    elif len(parts) == 2:
        if is_state(parts[1]):
            state = parts[1]
        elif not is_invalid_city_state(parts[1]):
            city = parts[1]
        address = parts[0]
    else:
        last = parts[-1]
        second_last = parts[-2]
        if is_state(last) and not is_invalid_city_state(last):
            state = last
            if not is_invalid_city_state(second_last):
                city = second_last
                address = ", ".join(parts[:-2])
            else:
                address = ", ".join(parts[:-1])
        elif not is_invalid_city_state(last):
            city = last
            address = ", ".join(parts[:-1])
        else:
            address = ", ".join(parts)
    return pd.Series([address, city, state, postcode])



# --- Setup Global Logging ---
def setup_logging(queue=None, process_id=None):
    logger = logging.getLogger(f"scraper_{process_id or 'main'}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | Process-%(process)d | %(message)s')

    if queue:
        handler = QueueHandler(queue)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        file_handler = logging.FileHandler('scraper_log.txt', mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


# --- Worker Function (Place ID only) ---
def scrape_worker(process_id, company_data, driver_path, result_queue, debug=True):
    """
    Args:
        process_id (int): Process number.
        company_data (list): List of (id, place_id) tuples.
        driver_path (str): Path to ChromeDriver.
        result_queue (Queue): Queue for results.
    """
    log_queue = multiprocessing.Queue()
    logger = setup_logging(log_queue, process_id=process_id)
    listener = QueueListener(
        log_queue,
        logging.StreamHandler(),
        logging.FileHandler(f'scraper_process_{process_id}.log', mode='w')
    )
    listener.handlers[0].setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | Process-%(process)d | %(message)s'))
    listener.handlers[1].setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | Process-%(process)d | %(message)s'))
    listener.start()

    logger.info(f"Started with {len(company_data)} Place IDs (debug={debug})")

    scraper = GoogleMapsScraper(driver_path, debug=debug)
    results = []

    try:
        for id_, place_id in tqdm(company_data, total=len(company_data), desc=f"Process {process_id}", position=process_id):
            logger.info(f"Scraping Place ID: {place_id}")
            try:
                start_time = time.time()
                name_c, address_c, website, business_type, phone_number = scraper.scrap_company_details_by_place_id(place_id)

                # 🔹 Optional: parse address
                street, city, state, postcode = parse_address(address_c)

                elapsed = time.time() - start_time
                logger.info(f"Scraped {name_c} | {website} | Took {elapsed:.2f}s")
            except Exception as e:
                logger.error(f"Error scraping {place_id}: {str(e)}")
                name_c, street, city, state, postcode, website, business_type, phone_number = (
                    "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
                )

            results.append((id_, place_id, name_c, street, city, state, postcode, website, business_type, phone_number))

    finally:
        scraper.close()
        logger.info("ChromeDriver closed")
        listener.stop()

    result_queue.put(results)
    logger.info(f"Completed, scraped {len(results)} records")


# --- Main Script ---
if __name__ == "__main__":
    # Setup logger
    logger = setup_logging()
    logger.info("Starting Google Maps scraping with Place IDs...")

    # Config
    DRIVER_PATH = r"C:\Users\a.shittu\Downloads\chromedriver.exe"
    BATCH_SIZE = 30
    NUM_SESSIONS = 1
    DAILY_LIMIT = 4500  # adjust as needed

    # Load your input table (Excel)
    excel_pf = 'Testtrial_placeid.xlsx'
    placedid = pd.read_excel(excel_pf)
    df = placedid[placedid["Hit Count"] >= 15]  # Must contain columns: SF_id, Google_Place_id
    logger.info(f"Loaded {len(df)} rows from Excel")

    # Expand multiple place_ids separated by "|"
    df["Google_Place_id"] = df["Google_Place_id"].astype(str)
    df = df.assign(Google_Place_id=df["Google_Place_id"].str.split("|")).explode("Google_Place_id").reset_index(drop=True)

    # Convert to list of (id, place_id)
    all_company_data = list(zip(df["SF_id"], df["Google_Place_id"]))

    processed_total = 0
    batch_number = 0
    all_results = []  # To store results from all batches

    while processed_total < DAILY_LIMIT and all_company_data:
        batch_number += 1
        batch = all_company_data[:BATCH_SIZE]
        all_company_data = all_company_data[BATCH_SIZE:]

        # Split batch into chunks for parallel workers
        chunk_size = ceil(len(batch) / NUM_SESSIONS)
        chunks = [batch[i:i + chunk_size] for i in range(0, len(batch), chunk_size)]
        logger.info(f"Batch {batch_number}: Split into {len(chunks)} chunks: {[len(c) for c in chunks]}")

        # Start multiprocessing
        result_queue = multiprocessing.Queue()
        processes = []
        for i, chunk in enumerate(chunks):
            if chunk:
                p = multiprocessing.Process(
                    target=scrape_worker,
                    args=(i + 1, chunk, DRIVER_PATH, result_queue, True)  # debug=True for visible browser
                )
                processes.append(p)
                p.start()

        # Wait for all processes
        for p in processes:
            p.join()

        # Collect results safely from all processes
        batch_results = []
        for _ in processes:
            batch_results.extend(result_queue.get())

        # Append batch results to all_results
        all_results.extend(batch_results)
        logger.info(f"Batch {batch_number}: Scraped {len(batch_results)} results")

        processed_total += len(batch_results)
        logger.info(f"Processed total so far: {processed_total}")

    # Convert all results to DataFrame
    df_results = pd.DataFrame(all_results, columns=[
        "SF_id", "Google_Place_id", "Company Name", "Street", "City", "State", "Postcode",
        "Website", "Business Type", "Phone Number"
    ])
    
    logger.info(f"Total scraped results: {len(df_results)}")
    
    # Perform the inner join so as to extract the company ID 
    df_merge= pd.merge(df_results,df, on = "Google_Place_id", how='inner')
    
    #drop duplicates
    df_merge = df_merge.drop_duplicates(subset = ['Google_Place_id'])
    
    Final_result = df_merge[[
        "SF_id_x", "Google_Place_id", "Search_Term", "Company Name", "Street", "City", "State", "Postcode",
        "Website", "Business Type", "Phone Number","phone_number"
    ]].rename(columns={"SF_id_x": "SF_id"})


    # Save all results to Excel
    excel_file = "scraped_results.xlsx"
    Final_result.to_excel(excel_file, index=False, engine="openpyxl")
    logger.info(f"All results saved to {excel_file}")

    logger.info("Scraping completed ✅")    
    
    #The levesthin complexity comparism process
    def normalize_phone(phone):
        """Remove spaces, +, and leading zeros for fair comparison"""
        if pd.isna(phone):
            return ""
        return phone.replace(" ", "").replace("+", "").lstrip("0")
    
    def calculate_similarity(row):
        # --- Name similarity ---
        search_name = row["Search_Term"].split(",")[0].strip().lower()
        company_name = str(row["Company Name"]).strip().lower()
        name_score = fuzz.token_sort_ratio(search_name, company_name)
    
        # --- Phone similarity ---
        search_phone = normalize_phone(str(row["Phone Number"]))
        company_phone = normalize_phone(str(row["phone_number"]))
        phone_score = fuzz.ratio(search_phone, company_phone) if search_phone and company_phone else 0
    
        # --- Final average ---
        final_score = (name_score + phone_score) / 2
        return pd.Series([name_score, phone_score, final_score])
    
    # Apply function
    Final_result[["Name_Similarity", "Phone_Similarity", "Final_Score"]] = Final_result.apply(calculate_similarity, axis=1)

    
    df_results.to_excel("Raw_results.xlsx",index=False,engine = "openpyxl")
    
    
