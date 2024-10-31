# import logging
# import time
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.chrome.service import Service
# from selenium.common.exceptions import UnexpectedAlertPresentException
# from selenium.webdriver.common.alert import Alert
# from webdriver_manager.chrome import ChromeDriverManager
# from selenium.webdriver.chrome.options import Options

# # Set up logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # Set up Chrome options and driver
# chrome_options = Options()
# chrome_options.add_argument("--disable-javascript")
# # chrome_options.add_argument("--headless")  # Optional: Run in headless mode if you don't need a UI
# driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# BASE_URL = "https://mobiletvshows.site/"
# SEARCH_TERM = "silicon valley"  # Replace with your actual search term

# try:
#     # Step 1: Navigate to the base URL
#     driver.get(BASE_URL)
#     logger.info("Navigated to %s", BASE_URL)
    
#     # Step 2: Locate the search bar and perform a search
#     search_bar = driver.find_element(By.ID, "searchname")  # Replace "searchname" with actual search bar ID
#     search_bar.send_keys(SEARCH_TERM)
#     search_bar.send_keys(Keys.RETURN)
#     logger.info("Performed search for %s", SEARCH_TERM)
#     time.sleep(10)  # Wait for results to load
    
#     # Step 3: Click the first search result
#     search_result = driver.find_element(By.CSS_SELECTOR, ".mainbox3 > a")  # Replace with actual CSS selector
#     search_result.click()
#     logger.info("Clicked on the first search result")
#     time.sleep(2)
    
#     # Step 4: Get all season links
#     season_links = driver.find_elements(By.CSS_SELECTOR, ".mainbox2 > a")  # Replace with actual CSS selector
#     for season_link in season_links:
#         logger.info("Opening season link: %s", season_link.text)
#         season_link.click()
#         time.sleep(2)
        
#         # Step 5: Get all episode links for the current season
#         episode_links = driver.find_elements(By.CSS_SELECTOR, ".mainbox > a")  # Replace with actual CSS selector
#         for episode_link in episode_links:
#             logger.info("Opening episode link: %s", episode_link.text)
#             episode_link.click()
#             time.sleep(2)
            
#             # Step 6: Go to the download page
#             download_page_link = driver.find_element(By.ID, "dlink2")  # Replace with actual ID
#             download_page_link.click()
#             logger.info("Navigated to download page")
#             time.sleep(2)
            
#             # Step 7: Click the final download button
#             download_button = driver.find_element(By.ID, "flink2")  # Replace with actual ID
#             download_button.click()
#             logger.info("Initiated download")
#             time.sleep(5)  # Allow time for download to start
            
#             # Go back to the season page after each episode
#             driver.back()
#             time.sleep(2)
        
#         # Go back to the main page after each season
#         driver.back()
#         time.sleep(2)
# except UnexpectedAlertPresentException as rr:
#     alert_text = Alert(driver).text
#     assert alert_text ==  "Download the Official Android App for FzMovies + FzTvSeries = FzStudios"
#     logger.error(f"Alert happend {rr}")
#     Alert(driver).dismiss()

# finally:
#     # Step 8: Close the driver
#     driver.quit()
#     logger.info("Closed the browser")

import re
import logging
import time
import requests
import threading
from bs4 import BeautifulSoup
from utils import download_file

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://mobiletvshows.site/"
SEARCH_TERM = "silicon valley"  # Replace with your actual search term

session = requests.Session()

ALL_EPISODE_LINKS = []

def get_soup(url):
    """Fetches the page content and returns a BeautifulSoup object."""
    response = session.get(url)
    # logger.info(f"Response text = {response.text}")
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser')

# def download_file(url, **kwargs):
#     episode_name = kwargs.get("name")

#     sanitized_name = re.sub(r'[\\/*?:"<>|]', "_", episode_name)
#     # Extract file extension from the URL if not provided in `episode_name`

#     file_extension = ".mp4"
#     sanitized_name += file_extension

#     with requests.get(url, stream=True) as r:
#         r.raise_for_status()
#         with open(sanitized_name, 'wb') as f:
#             for chunk in r.iter_content(chunk_size=10000): 
#                 f.write(chunk)
#     return True


try:
    # Step 1: Perform a searchhttps://mobiletvshows.site/search.php?search=silicon+valley&beginsearch=Search&vsearch=&by=series=
    search_url = f"{BASE_URL}search.php?search={SEARCH_TERM.replace(' ', '+')}&beginsearch=Search&vsearch=&by=series="
    logger.info("Navigating to search URL: %s", search_url)
    soup = get_soup(search_url)
    time.sleep(2)
    
    # Step 2: Locate the first search result link
    search_result = soup.select_one(".mainbox3 table span a")  # Replace with actual CSS selector if different
    if not search_result:
        logger.error("No search results found.")
    else:
        show_url = BASE_URL + search_result["href"]
        logger.info("Opening first search result link: %s", show_url)
        
        # Step 3: Get all season links
        soup = get_soup(show_url)
        season_links = soup.select(".mainbox2 > a")  # Replace with actual CSS selector if different
        
        for season_link in season_links:
            season_url = BASE_URL + season_link["href"]
            logger.info("Opening season link: %s", season_link.text)
            soup = get_soup(season_url)
            time.sleep(2)
            
            # Step 4: Get all episode links for the current season
            episode_links_parent = soup.find_all(class_="mainbox")  # Replace with actual CSS selector if different
            # print("Episode links = ", episode_links_parent)
            for episode_link in episode_links_parent:
                link = episode_link.find('a') # get the first link beacuse if is two mp4 or webm
                episode_name = str(episode_link.find("b").text)
                logger.error(episode_name)
                episode_url = BASE_URL + link["href"]
                ALL_EPISODE_LINKS.append(episode_url)
                logger.info("Opening episode link: %s", link.text)
                soup = get_soup(episode_url)
                
                # Step 5: Go to the download page
                download_page_link = soup.select_one("#dlink2")  # Replace with actual ID if different
                if download_page_link:
                    download_url = BASE_URL + download_page_link["href"]
                    logger.info("Navigated to download page: %s", download_url)
                    soup = get_soup(download_url)
                    
                #     # Step 6: Click the final download button
                    download_button = soup.select_one(".downloadlinks2 input")  # Replace with actual ID if different
                    if download_button:
                        final_download_url = download_button['value']
                        logger.info("Final download URL: %s", final_download_url)
                        episode_name = episode_name + ".mp4"
                        # Here, you might download the file or handle it as needed.
                        download_file(final_download_url, local_filepath=episode_name)
                    else:
                        logger.warning("Download button not found on the download page.")
                else:
                    logger.warning("Download page link not found on episode page.")
                
finally:
    logger.info("Finished scraping.")

