
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





    async def get_season_links(self, session, show_url):
        soup = await self.get_soup(session, show_url)
        return soup.select(".mainbox2 > a")[:self.number_of_seasons]

    async def scrape_season(self, session, season_link):
        season_url = self.baseurl + season_link["href"]
        logger.debug("Fetching season link: %s", season_link.text)
        
        soup = await self.get_soup(session, season_url)
        episode_links_parent = soup.find_all(class_="mainbox")
        
        # Gather all episode scraping concurrently
        await asyncio.gather(*[self.scrape_episode(session, episode_link) for episode_link in episode_links_parent])
        logger.info(f"Completed downloading season: {season_link.text}")

    async def scrape_episode(self, session, episode_link):
        link = episode_link.find('a')
        episode_name = str(episode_link.find("b").text) + ".mp4"
        
        if link:
            episode_url = self.baseurl + link["href"]
            logger.info("Opening episode link: %s", link.text)
            soup = await self.get_soup(session, episode_url)
            
            download_url = await self.get_download_url(session, soup)
            if download_url:
                self.download_links.append({"link": download_url, "name": episode_name})
                logger.info(f"Added download link for {episode_name}")
            else:
                logger.warning("Download link not found for episode.")

    async def get_download_url(self, session, soup):
        download_page_link = soup.select_one("#dlink2")
        if download_page_link:
            download_url = self.baseurl + download_page_link["href"]
            soup = await self.get_soup(session, download_url)
            
            download_button = soup.select_one(".downloadlinks2 input")
            if download_button:
                return download_button['value']
        return None


