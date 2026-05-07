import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from app.core.config import AppConfig
from app.core.models import DownloadEvent
from app.core.orchestrator import DownloadOrchestrator

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DownloadRecord:
    name: str
    status: str = "pending"
    downloaded_bytes: int = 0
    total_bytes: int = 0
    detail: str | None = None

    def progress_percent(self) -> int:
        if self.total_bytes <= 0:
            return 0
        return int((self.downloaded_bytes / self.total_bytes) * 100)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "detail": self.detail,
            "progress_percent": self.progress_percent(),
        }


@dataclass(slots=True)
class BrowserJob:
    job_id: str
    title: str
    media_type: str
    season: int | None
    episode: int | None
    concurrent: int
    max_downloads: int | None
    status: str = "queued"
    message: str = "Waiting to start"
    downloads: dict[str, DownloadRecord] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    direct_url: str | None = None

    def __post_init__(self) -> None:
        self.pause_event.set()

    def summary(self) -> dict[str, Any]:
        items = [record.to_dict() for record in self.downloads.values()]
        completed = sum(1 for item in items if item["status"] == "completed")
        failed = sum(1 for item in items if item["status"] == "failed")
        cancelled = sum(1 for item in items if item["status"] == "cancelled")
        active = sum(1 for item in items if item["status"] in {"starting", "downloading"})
        paused = sum(1 for item in items if item["status"] == "paused")
        queued = sum(1 for item in items if item["status"] in {"pending", "queued"})
        return {
            "job_id": self.job_id,
            "title": self.title,
            "media_type": self.media_type,
            "season": self.season,
            "episode": self.episode,
            "concurrent": self.concurrent,
            "max_downloads": self.max_downloads,
            "status": self.status,
            "message": self.message,
            "is_paused": not self.pause_event.is_set(),
            "is_cancelled": self.cancel_event.is_set(),
            "downloads": items,
            "counts": {
                "total": len(items),
                "completed": completed,
                "failed": failed,
                "cancelled": cancelled,
                "active": active,
                "paused": paused,
                "queued": queued,
            },
        }


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, BrowserJob] = {}

    def create_job(
        self,
        *,
        title: str,
        media_type: str,
        season: int | None,
        episode: int | None,
        concurrent: int,
        max_downloads: int | None,
    ) -> BrowserJob:
        job = BrowserJob(
            job_id=uuid.uuid4().hex[:10],
            title=title,
            media_type=media_type,
            season=season,
            episode=episode,
            concurrent=concurrent,
            max_downloads=max_downloads,
        )
        self.jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> BrowserJob | None:
        return self.jobs.get(job_id)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FZbot Web UI</title>
  <style>
    :root {{
      --bg: #f4efe8;
      --panel: rgba(255, 252, 247, 0.9);
      --ink: #1f2933;
      --accent: #d66a1f;
      --accent-dark: #9b3d12;
      --muted: #6b7280;
      --line: rgba(31, 41, 51, 0.12);
      --success: #1f7a4f;
      --error: #b42318;
      --shadow: 0 22px 45px rgba(94, 57, 30, 0.16);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(214, 106, 31, 0.18), transparent 28%),
        radial-gradient(circle at bottom right, rgba(54, 123, 186, 0.18), transparent 22%),
        linear-gradient(135deg, #f7f1e8 0%, #efe4d6 100%);
      min-height: 100vh;
    }}
    .shell {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 40px 20px 56px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 24px;
      align-items: start;
      margin-bottom: 24px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }}
    .intro {{
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(2.5rem, 5vw, 4.6rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }}
    .lede {{
      margin: 0;
      font-size: 1.08rem;
      line-height: 1.7;
      color: var(--muted);
      max-width: 36rem;
    }}
    .meta {{
      display: grid;
      gap: 12px;
      padding: 28px;
    }}
    .meta strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent-dark);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 24px;
    }}
    .form-card, .jobs-card {{
      padding: 24px;
    }}
    form {{
      display: grid;
      gap: 16px;
    }}
    label {{
      display: grid;
      gap: 8px;
      font-size: 0.98rem;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      font: inherit;
      background: rgba(255, 255, 255, 0.88);
    }}
    .row {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 14px 18px;
      font: inherit;
      font-weight: 700;
      color: white;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%);
      cursor: pointer;
    }}
    .hint {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .job-list {{
      display: grid;
      gap: 14px;
    }}
    .job-item {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
      background: rgba(255,255,255,0.7);
    }}
    .job-item a {{
      color: inherit;
      text-decoration: none;
      display: block;
    }}
    .job-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 6px;
      font-weight: 700;
    }}
    .job-meta {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .badge {{
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      background: rgba(214, 106, 31, 0.12);
      color: var(--accent-dark);
      white-space: nowrap;
    }}
    @media (max-width: 860px) {{
      .hero, .grid, .row {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <article class="card intro">
        <h1>FZbot<br>Browser Desk</h1>
        <p class="lede">Search and download TV series from a local browser UI while the same shared Python engine keeps powering the CLI underneath.</p>
      </article>
      <aside class="card meta">
        <div>
          <strong>Mode</strong>
          <span>Local web UI over the async downloader</span>
        </div>
        <div>
          <strong>Current scope</strong>
          <span>Series downloads, queue tracking, live progress polling</span>
        </div>
        <div>
          <strong>Still supported</strong>
          <span>CLI remains available for scriptable usage</span>
        </div>
      </aside>
    </section>

    <section class="grid">
      <article class="card form-card">
        <h2>Start a download</h2>
        <form method="post" action="/jobs">
          <label>
            Title
            <input name="title" placeholder="e.g. Breaking Bad" required>
          </label>

          <div class="row">
            <label>
              Media type
              <select name="media_type">
                <option value="series" selected>Series</option>
                <option value="movie">Movie</option>
              </select>
            </label>
            <label>
              Concurrent downloads
              <input type="number" name="concurrent" min="1" max="10" value="3">
            </label>
          </div>

          <div class="row">
            <label>
              Season
              <input type="number" name="season" min="1" placeholder="Optional">
            </label>
            <label>
              Episode
              <input type="number" name="episode" min="1" placeholder="Optional">
            </label>
          </div>

          <div class="row">
            <label>
              Max downloads
              <input type="number" name="max_downloads" min="1" value="10">
            </label>
            <label>
              Direct series URL
              <input name="url" placeholder="Optional mobiletvshows URL">
            </label>
          </div>

          <button type="submit">Launch download job</button>
        </form>
        <p class="hint">The UI starts the work in the background, then opens a live status page that refreshes itself as each episode moves through the queue.</p>
      </article>

      <article class="card jobs-card">
        <h2>Recent jobs</h2>
        <div class="job-list">
          {job_items}
        </div>
      </article>
    </section>
  </main>
</body>
</html>
"""


JOB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | FZbot Job</title>
  <style>
    :root {{
      --bg: #f7f1e8;
      --ink: #1f2933;
      --muted: #667085;
      --card: rgba(255,255,255,0.88);
      --line: rgba(31, 41, 51, 0.12);
      --shadow: 0 18px 40px rgba(82, 47, 23, 0.12);
      --accent: #d66a1f;
      --accent-dark: #9b3d12;
      --ok: #1f7a4f;
      --bad: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top right, rgba(214, 106, 31, 0.16), transparent 28%),
        linear-gradient(180deg, #f8f3eb 0%, #efe3d1 100%);
      color: var(--ink);
    }}
    .shell {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 36px 20px 56px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 24px;
    }}
    .topbar a {{
      color: var(--accent-dark);
      text-decoration: none;
      font-weight: 700;
    }}
    .hero, .list {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 24px;
    }}
    .hero {{
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(2rem, 4vw, 3.4rem);
      line-height: 1;
      letter-spacing: -0.04em;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-top: 22px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,0.75);
    }}
    .stat strong {{
      display: block;
      font-size: 1.4rem;
    }}
    .list-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 16px;
    }}
    .downloads {{
      display: grid;
      gap: 14px;
    }}
    .download {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,0.72);
    }}
    .download-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 8px;
    }}
    .status {{
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.82rem;
      text-transform: capitalize;
      background: rgba(214, 106, 31, 0.12);
      color: var(--accent-dark);
    }}
    .status.completed {{
      background: rgba(31, 122, 79, 0.12);
      color: var(--ok);
    }}
    .status.failed {{
      background: rgba(180, 35, 24, 0.12);
      color: var(--bad);
    }}
    .status.cancelled {{
      background: rgba(102, 112, 133, 0.16);
      color: var(--muted);
    }}
    .status.paused {{
      background: rgba(54, 123, 186, 0.14);
      color: #1f4c7a;
    }}
    .controls {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 20px;
    }}
    .control {{
      border: 0;
      border-radius: 999px;
      padding: 12px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .control.pause {{
      color: white;
      background: linear-gradient(135deg, #367bba 0%, #1f4c7a 100%);
    }}
    .control.cancel {{
      color: white;
      background: linear-gradient(135deg, #b42318 0%, #7a1d14 100%);
    }}
    .control:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
    .progress {{
      height: 10px;
      border-radius: 999px;
      background: rgba(31, 41, 51, 0.08);
      overflow: hidden;
      margin: 8px 0;
    }}
    .bar {{
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent) 0%, #f1ac59 100%);
      transition: width 0.25s ease;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    @media (max-width: 860px) {{
      .summary {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .download-head, .topbar, .list-head {{
        flex-direction: column;
        align-items: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <a href="/">Back to launcher</a>
      <div id="job-state">{status_label}</div>
    </div>

    <section class="hero">
      <h1>{title}</h1>
      <p id="message">{message}</p>
      <div class="summary">
        <div class="stat"><span>Total files</span><strong id="count-total">0</strong></div>
        <div class="stat"><span>Completed</span><strong id="count-completed">0</strong></div>
        <div class="stat"><span>Active</span><strong id="count-active">0</strong></div>
        <div class="stat"><span>Failed</span><strong id="count-failed">0</strong></div>
      </div>
      <div class="controls">
        <button id="pause-button" class="control pause" type="button">Pause</button>
        <button id="cancel-button" class="control cancel" type="button">Cancel all</button>
      </div>
    </section>

    <section class="list">
      <div class="list-head">
        <h2>Episodes</h2>
        <span class="meta">Page polls <code>/api/jobs/{job_id}</code> for live updates.</span>
      </div>
      <div class="downloads" id="downloads"></div>
    </section>
  </main>

  <script>
    const jobId = {job_json};

    function formatBytes(value) {{
      if (!value) return "0 B";
      const units = ["B", "KB", "MB", "GB"];
      let size = value;
      let unit = 0;
      while (size >= 1024 && unit < units.length - 1) {{
        size /= 1024;
        unit += 1;
      }}
      return `${{size.toFixed(size >= 10 || unit === 0 ? 0 : 1)}} ${{units[unit]}}`;
    }}

    function renderJob(data) {{
      document.title = `${{data.title}} | FZbot Job`;
      document.getElementById("job-state").textContent = `Status: ${{data.status}}`;
      document.getElementById("message").textContent = data.message;
      document.getElementById("count-total").textContent = data.counts.total;
      document.getElementById("count-completed").textContent = data.counts.completed;
      document.getElementById("count-active").textContent = data.counts.active;
      document.getElementById("count-failed").textContent = data.counts.failed;
      const pauseButton = document.getElementById("pause-button");
      const cancelButton = document.getElementById("cancel-button");
      pauseButton.textContent = data.is_paused ? "Resume" : "Pause";
      pauseButton.disabled = data.is_cancelled || ["completed", "failed", "completed_with_errors", "cancelled"].includes(data.status);
      cancelButton.disabled = data.is_cancelled || ["completed", "failed", "completed_with_errors", "cancelled"].includes(data.status);

      const root = document.getElementById("downloads");
      if (!data.downloads.length) {{
        root.innerHTML = `<div class="download"><div class="meta">The queue is still being prepared.</div></div>`;
        return;
      }}

      root.innerHTML = data.downloads.map((item) => `
        <article class="download">
          <div class="download-head">
            <strong>${{item.name}}</strong>
            <span class="status ${{item.status}}">${{item.status}}</span>
          </div>
          <div class="progress"><div class="bar" style="width: ${{item.progress_percent}}%"></div></div>
          <div class="meta">
            ${{formatBytes(item.downloaded_bytes)}} / ${{formatBytes(item.total_bytes)}}
            ${{item.detail ? ` • ${{item.detail}}` : ""}}
          </div>
        </article>
      `).join("");
    }}

    async function sendControl(action) {{
      const response = await fetch(`/jobs/${{jobId}}/${{action}}`, {{
        method: "POST"
      }});
      if (!response.ok) {{
        throw new Error(`HTTP ${{response.status}}`);
      }}
      const data = await response.json();
      renderJob(data);
    }}

    document.getElementById("pause-button").addEventListener("click", async () => {{
      try {{
        await sendControl("pause");
      }} catch (error) {{
        document.getElementById("message").textContent = `Pause failed: ${{error.message}}`;
      }}
    }});

    document.getElementById("cancel-button").addEventListener("click", async () => {{
      try {{
        await sendControl("cancel");
      }} catch (error) {{
        document.getElementById("message").textContent = `Cancel failed: ${{error.message}}`;
      }}
    }});

    async function poll() {{
      try {{
        const response = await fetch(`/api/jobs/${{jobId}}`);
        if (!response.ok) {{
          throw new Error(`HTTP ${{response.status}}`);
        }}
        const data = await response.json();
        renderJob(data);
        if (!["completed", "failed", "completed_with_errors"].includes(data.status)) {{
          setTimeout(poll, 1200);
        }}
      }} catch (error) {{
        document.getElementById("message").textContent = `Polling failed: ${{error.message}}`;
        setTimeout(poll, 2500);
      }}
    }}

    poll();
  </script>
</body>
</html>
"""


def _to_int(raw: str | None) -> int | None:
    if not raw:
        return None
    return int(raw)


def _render_index(store: JobStore) -> str:
    job_items = []
    for job in reversed(list(store.jobs.values())[-8:]):
        job_items.append(
            """
            <article class="job-item">
              <a href="/jobs/{job_id}">
                <div class="job-head">
                  <span>{title}</span>
                  <span class="badge">{status}</span>
                </div>
                <div class="job-meta">Season: {season} • Episode: {episode} • Concurrency: {concurrent}</div>
              </a>
            </article>
            """.format(
                job_id=job.job_id,
                title=job.title,
                status=job.status,
                season=job.season or "all",
                episode=job.episode or "all",
                concurrent=job.concurrent,
            )
        )
    if not job_items:
        job_items.append('<div class="job-item"><div class="job-meta">No jobs yet. Start one from the form.</div></div>')
    return INDEX_HTML.format(job_items="".join(job_items))


def _render_job(job: BrowserJob) -> str:
    return JOB_HTML.format(
        title=job.title,
        message=job.message,
        status_label=f"Status: {job.status}",
        job_id=job.job_id,
        job_json=json.dumps(job.job_id),
    )


async def index(request: web.Request) -> web.Response:
    store: JobStore = request.app["job_store"]
    return web.Response(text=_render_index(store), content_type="text/html")


async def create_job(request: web.Request) -> web.StreamResponse:
    store: JobStore = request.app["job_store"]
    form = await request.post()

    title = str(form.get("title", "")).strip()
    if not title:
        raise web.HTTPBadRequest(text="title is required")

    job = store.create_job(
        title=title,
        media_type=str(form.get("media_type", "series")),
        season=_to_int(form.get("season")),
        episode=_to_int(form.get("episode")),
        concurrent=_to_int(form.get("concurrent")) or 3,
        max_downloads=_to_int(form.get("max_downloads")) or 10,
    )

    url = str(form.get("url", "")).strip() or None
    job.direct_url = url
    job.message = "Preparing series lookup and download queue"
    job.task = asyncio.create_task(_run_job(job))
    raise web.HTTPFound(location=f"/jobs/{job.job_id}")


async def job_page(request: web.Request) -> web.Response:
    store: JobStore = request.app["job_store"]
    job = store.get(request.match_info["job_id"])
    if not job:
        raise web.HTTPNotFound(text="job not found")
    return web.Response(text=_render_job(job), content_type="text/html")


async def job_api(request: web.Request) -> web.Response:
    store: JobStore = request.app["job_store"]
    job = store.get(request.match_info["job_id"])
    if not job:
        raise web.HTTPNotFound(text="job not found")
    return web.json_response(job.summary())


async def pause_job(request: web.Request) -> web.Response:
    store: JobStore = request.app["job_store"]
    job = store.get(request.match_info["job_id"])
    if not job:
        raise web.HTTPNotFound(text="job not found")

    if job.cancel_event.is_set() or job.status in {"completed", "failed", "completed_with_errors", "cancelled"}:
        return web.json_response(job.summary())

    if job.pause_event.is_set():
        job.pause_event.clear()
        job.status = "paused"
        job.message = "Pause requested. Active downloads will stop at the next chunk boundary."
    else:
        job.pause_event.set()
        job.status = "running"
        job.message = "Resuming downloads."

    return web.json_response(job.summary())


async def cancel_job(request: web.Request) -> web.Response:
    store: JobStore = request.app["job_store"]
    job = store.get(request.match_info["job_id"])
    if not job:
        raise web.HTTPNotFound(text="job not found")

    job.cancel_event.set()
    job.pause_event.set()
    job.status = "cancelled"
    job.message = "Cancellation requested. Active downloads are stopping."

    for record in job.downloads.values():
        if record.status not in {"completed", "failed", "cancelled"}:
            record.status = "cancelled"
            record.detail = "Cancelled by user"

    if job.task and not job.task.done():
        job.task.cancel()

    return web.json_response(job.summary())


def _handle_event(job: BrowserJob, event: DownloadEvent) -> None:
    record = job.downloads.setdefault(event.name, DownloadRecord(name=event.name))
    record.status = event.status
    record.downloaded_bytes = event.downloaded_bytes
    record.total_bytes = event.total_bytes
    record.detail = event.detail

    if event.status == "queued":
        job.status = "running"
        job.message = "Queue prepared. Waiting for worker slots."
    elif event.status == "starting":
        job.status = "running"
        job.message = f"Starting {event.name}"
    elif event.status == "downloading":
        job.status = "running"
        job.message = f"Downloading {event.name}"
    elif event.status == "paused":
        job.status = "paused"
        job.message = f"Paused {event.name}"
    elif event.status == "completed":
        job.message = f"Completed {event.name}"
    elif event.status == "cancelled":
        job.message = f"Cancelled {event.name}"
    elif event.status == "failed":
        job.message = f"Failed {event.name}"


async def _run_job(job: BrowserJob) -> None:
    config = AppConfig(
        title=job.title,
        media_type=job.media_type,
        season=job.season,
        max_downloads=job.max_downloads,
        specific_episode=job.episode,
        url=job.direct_url,
        concurrent_downloads=job.concurrent,
        request_timeout_seconds=None,
    )
    orchestrator = DownloadOrchestrator(
        config=config,
        event_callback=lambda event: _handle_event(job, event),
        pause_event=job.pause_event,
        cancel_event=job.cancel_event,
    )

    try:
        job.status = "running"
        job.message = "Collecting episode links from MobileTVShows"
        downloads = await orchestrator.run()
        if job.cancel_event.is_set():
            job.status = "cancelled"
            job.message = "All remaining downloads were cancelled."
            return
        if not downloads:
            if job.media_type == "movie":
                job.status = "failed"
                job.message = "Movie downloads are not implemented yet."
            else:
                job.status = "failed"
                job.message = "No downloads were found for the requested title."
            return

        if any(record.status == "failed" for record in job.downloads.values()):
            job.status = "completed_with_errors"
            job.message = "Download finished with some failed items."
        else:
            job.status = "completed"
            job.message = "All downloads finished."
    except asyncio.CancelledError:
        logger.info("Job %s cancelled by user", job.job_id)
        job.status = "cancelled"
        job.message = "All remaining downloads were cancelled."
    except Exception:
        logger.exception("Job %s failed", job.job_id)
        job.status = "failed"
        job.message = "The job crashed unexpectedly. Check logs for details."


def create_app() -> web.Application:
    app = web.Application()
    app["job_store"] = JobStore()
    app.router.add_get("/", index)
    app.router.add_post("/jobs", create_job)
    app.router.add_get("/jobs/{job_id}", job_page)
    app.router.add_get("/api/jobs/{job_id}", job_api)
    app.router.add_post("/jobs/{job_id}/pause", pause_job)
    app.router.add_post("/jobs/{job_id}/cancel", cancel_job)
    return app


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_app(), host=host, port=port)
