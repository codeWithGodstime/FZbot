
import datetime
import os
import requests
import threading as th

keep_going = True
def key_capture_thread():
    global keep_going
    input()
    keep_going = False
pkey_capture = th.Thread(target=key_capture_thread, args=(), name='key_capture_process', daemon=True).start()

def download_file(url, local_filepath):
    #assumptions:
    #  headers contain Content-Length:
    #  headers contain Accept-Ranges: bytes
    #  stream is not encoded (otherwise start bytes are not known, unless this is stored seperately)
    
    # chunk_size = 1048576 #1MB
    chunk_size = 8096 #8KB
    # chunk_size = 1024 #1KB
    decoded_bytes_downloaded_this_session = 0
    start_time = datetime.datetime.now()
    if os.path.exists(local_filepath):
        decoded_bytes_downloaded = os.path.getsize(local_filepath)
    else:
        decoded_bytes_downloaded = 0
    with requests.Session() as s:
        with s.get(url, stream=True) as r:
            #check for required headers:
            if 'Content-Length' not in r.headers:
                print('STOP: request headers do not contain Content-Length')
                return
            if ('Accept-Ranges','bytes') not in r.headers.items():
                print('STOP: request headers do not contain Accept-Ranges: bytes')
                with s.get(url) as r:
                    print(str(r.content, encoding='iso-8859-1'))
                return
        content_length = int(r.headers['Content-Length'])
        
        if decoded_bytes_downloaded>=content_length:
                print('STOP: file already downloaded. decoded_bytes_downloaded>=r.headers[Content-Length]; {}>={}'.format(decoded_bytes_downloaded,r.headers['Content-Length']))
                return
        if decoded_bytes_downloaded>0:
            s.headers['Range'] = 'bytes={}-{}'.format(decoded_bytes_downloaded, content_length-1) #range is inclusive
            print('Retrieving byte range (inclusive) {}-{}'.format(decoded_bytes_downloaded, content_length-1))
        with s.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filepath, mode='ab') as fwrite:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    decoded_bytes_downloaded+=len(chunk)
                    decoded_bytes_downloaded_this_session+=len(chunk)
                    time_taken:datetime.timedelta = (datetime.datetime.now() - start_time)
                    seconds_per_byte = time_taken.total_seconds()/decoded_bytes_downloaded_this_session
                    remaining_bytes = content_length-decoded_bytes_downloaded
                    remaining_seconds = seconds_per_byte * remaining_bytes
                    remaining_time = datetime.timedelta(seconds=remaining_seconds)
                    #print updated statistics here
                    fwrite.write(chunk)
                    if not keep_going:
                        break



async def scrape_seasons_link(self, series_url):
        soup = await self.get_soup(self.session, series_url)
        series_links = soup.select(".mainbox2 > a")
        episode_link_parents = soup.find_all(class_="mainbox")
        print("ALL EP", episode_link_parents)

        if self.settings['season']:
            print("SINGLE SEASON")
            soup = await self.get_soup(self.session, series_url)
            series_link = series_links[self.settings['season'] - 1]

            # single episode page
            season_url = self.baseurl + series_link["href"]
            logger.info("Scraping %s", series_link.text)

            soup = await self.get_soup(self.session, season_url)

            if self.settings['specific_episode']:
                print("SINGLE EPISODE")

                episode_link_parent = episode_link_parents[self.settings['specific_episode'] - 1]
                logger.info("The number of episode for %s is %s", series_link.text, episode_link_parent)

                await self.scrape_episode_link(episode_link_parent)
            else:
   
                logger.info("The number of episode for %s is %s", series_link.text, len(episode_link_parents)) 
                await asyncio.gather(*[self.scrape_episode_link( episode_link) for episode_link in episode_link_parents])

        else:
            print("getting all series")
            pass

    async def scrape_episode_link(self, episode_link: BeautifulSoup):
        try:
            logger.debug("Scraping %s\n", episode_link.find('small').text)

            link = episode_link.find('a')

            if link:
                episode_url = self.baseurl + link["href"]
                logger.info("Opening episode link: %s", link.text)  # high mp4, avi, webm

                soup = await self.get_soup(self.session, episode_url)

                episode_name = episode_link.find("b").text.strip()

                # Check the type of link and format the episode name
                if "high mp4" in link.text.lower():
                    episode_name = f"{episode_name}.mp4"  # Add .mp4 extension for high mp4
                else:
                    episode_name = f"{episode_name}.{link.text.lower()[1:-1]}"  # Use link text as extension

                logger.info("Formatted episode name with extension to save with: %s", episode_name)

                # Scrape the download link
                download_url = await self.scrape_download_link(soup)
                if download_url:
                    # Store the download link and episode name
                    self.download_links.append({"link": download_url, "name": episode_name})
                    logger.info(f"Added download link for {episode_name}")
                else:
                    # Log warning if no download link is found
                    logger.warning("Download link not found for episode %s", episode_name)
        except Exception as e:
            # Log critical error for unhandled exceptions
            logger.critical(f"An error occurred while scraping episode link: {e}")

    async def scrape_download_link(self, soup: BeautifulSoup):
        download_page_link = soup.select_one("#dlink2")
        if download_page_link:
            download_url = self.baseurl + download_page_link["href"]
            soup = await self.get_soup(self.session, download_url)

            download_button = soup.select(".downloadlinks2 input")[1]
            if download_button:
                return download_button['value']
        return None
