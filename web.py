import aiohttp
from aiohttp import web
import aiohttp_jinja2
import jinja2
import os
import json
import asyncio
from bot import SeriesDownloader

# Store active downloads and their progress
active_downloads = {}
# Store background tasks
background_tasks = set()

routes = web.RouteTableDef()

def track_task(task):
    """Add task to background tasks set"""
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

def update_progress(download_id, episode_name, progress):
    """Update download progress in active_downloads"""
    if download_id in active_downloads:
        download = active_downloads[download_id]
        # Find or create episode in episodes list
        episode = next((ep for ep in download['episodes'] if ep['name'] == episode_name), None)
        if episode is None:
            episode = {'name': episode_name, 'progress': 0}
            download['episodes'].append(episode)
        
        # Update episode progress
        episode['progress'] = progress
        
        # Calculate overall progress
        if download['episodes']:
            total_progress = sum(ep['progress'] for ep in download['episodes'])
            download['progress'] = total_progress / len(download['episodes'])

@routes.get('/')
@aiohttp_jinja2.template('index.html')
async def index(request):
    return {'active_downloads': active_downloads}

@routes.post('/download')
async def start_download(request):
    try:
        data = await request.json()
        title = data.get('title')
        season = data.get('season')
        specific_episode = data.get('specific_episode')
        limit_episode = data.get('limit_episode')

        if not title:
            return web.json_response({'error': 'Title is required'}, status=400)

        settings = {
            'title': title,
            'season': int(season) if season else None,
            'specific_episode': int(specific_episode) if specific_episode else None,
            'limit_episode': int(limit_episode) if limit_episode else None,
            'type': 'series',  # Since this is the series downloader interface
            'progress_callback': lambda name, progress: update_progress(download_id, name, progress)
        }

        # Create a unique ID for this download
        download_id = f"{title}_{len(active_downloads)}"
        active_downloads[download_id] = {
            'title': title,
            'status': 'starting',
            'progress': 0,
            'episodes': []
        }

        # Start download in background task
        task = asyncio.create_task(
            start_download_task(download_id, settings, request.app['client_session'])
        )
        track_task(task)

        return web.json_response({
            'status': 'success',
            'download_id': download_id
        })

    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

@routes.get('/status/{download_id}')
async def get_status(request):
    download_id = request.match_info['download_id']
    if download_id in active_downloads:
        return web.json_response(active_downloads[download_id])
    return web.json_response({'error': 'Download not found'}, status=404)

@routes.get('/status/all')
async def get_all_status(request):
    return web.json_response(active_downloads)

async def start_download_task(download_id, settings, session):
    try:
        scraper = SeriesDownloader(settings['title'], session, **settings)
        active_downloads[download_id]['status'] = 'downloading'
        await scraper.start()
        active_downloads[download_id]['status'] = 'completed'
    except Exception as e:
        active_downloads[download_id]['status'] = 'error'
        active_downloads[download_id]['error'] = str(e)

async def cleanup(app):
    """Cleanup background tasks and client session on shutdown"""
    # Cancel all background tasks
    for task in background_tasks:
        task.cancel()
    # Wait for all tasks to complete
    await asyncio.gather(*background_tasks, return_exceptions=True)
    # Close the client session
    await app['client_session'].close()

async def init_app():
    app = web.Application()
    app['client_session'] = aiohttp.ClientSession()
    
    # Setup templates
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader('templates')
    )
    
    # Add routes
    app.add_routes(routes)
    
    # Serve static files
    app.router.add_static('/static', 'static')
    
    # Setup cleanup
    app.on_cleanup.append(cleanup)
    
    return app

def main():
    # Create necessary directories
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    web.run_app(init_app(), host='localhost', port=8080)

if __name__ == '__main__':
    main()
