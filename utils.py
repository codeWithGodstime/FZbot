
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
        print("== ",content_length)
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




