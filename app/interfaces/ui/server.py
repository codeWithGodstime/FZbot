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


SHARED_STYLES = """
    :root {
      --space-bg: #050510;
      --space-surface: rgba(15, 23, 42, 0.8);
      --space-border: rgba(34, 211, 238, 0.2);
      --accent-cyan: #22d3ee;
      --accent-purple: #a855f7;
      --text-primary: #e2e8f0;
      --text-muted: #94a3b8;
      --success: #34d399;
      --error: #f87171;
      --warning: #fbbf24;
      --glow-cyan: 0 0 20px rgba(34, 211, 238, 0.3);
      --glow-purple: 0 0 24px rgba(168, 85, 247, 0.25);
      --shadow: 0 24px 48px rgba(0, 0, 0, 0.45);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Inter", system-ui, sans-serif;
      color: var(--text-primary);
      background: linear-gradient(160deg, #050510 0%, #0f172a 50%, #1e1b4b 100%);
      min-height: 100vh;
      position: relative;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        radial-gradient(1px 1px at 20px 30px, rgba(255,255,255,0.7), transparent),
        radial-gradient(1px 1px at 80px 120px, rgba(255,255,255,0.5), transparent),
        radial-gradient(1.5px 1.5px at 160px 60px, rgba(255,255,255,0.6), transparent),
        radial-gradient(1px 1px at 240px 180px, rgba(255,255,255,0.4), transparent),
        radial-gradient(1px 1px at 320px 90px, rgba(255,255,255,0.55), transparent),
        radial-gradient(1.5px 1.5px at 400px 200px, rgba(255,255,255,0.45), transparent),
        radial-gradient(1px 1px at 500px 40px, rgba(255,255,255,0.5), transparent),
        radial-gradient(1px 1px at 600px 150px, rgba(255,255,255,0.35), transparent);
      background-size: 650px 220px;
      opacity: 0.55;
      animation: twinkle 8s ease-in-out infinite alternate;
    }
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        radial-gradient(ellipse at 15% 10%, rgba(168, 85, 247, 0.18), transparent 45%),
        radial-gradient(ellipse at 85% 80%, rgba(34, 211, 238, 0.12), transparent 40%);
    }
    @keyframes twinkle {
      from { opacity: 0.4; }
      to { opacity: 0.7; }
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--accent-cyan); }
      50% { opacity: 0.5; box-shadow: 0 0 2px var(--accent-cyan); }
    }
    h1, h2, h3 {
      font-family: "Orbitron", sans-serif;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    h2 {
      margin: 0 0 20px;
      font-size: 1.1rem;
      color: var(--accent-cyan);
      text-transform: uppercase;
    }
    .site-header {
      position: sticky;
      top: 0;
      z-index: 100;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 24px;
      background: rgba(5, 5, 16, 0.85);
      border-bottom: 1px solid var(--space-border);
      backdrop-filter: blur(12px);
    }
    .site-header .brand {
      font-family: "Orbitron", sans-serif;
      font-size: 1rem;
      font-weight: 700;
      color: var(--accent-cyan);
      text-decoration: none;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .site-header .tagline {
      font-size: 0.8rem;
      color: var(--text-muted);
      letter-spacing: 0.06em;
    }
    .shell {
      max-width: 760px;
      margin: 0 auto;
      padding: 32px 20px 56px;
      position: relative;
      z-index: 1;
    }
    .shell.wide {
      max-width: 960px;
    }
    .card {
      background: var(--space-surface);
      border: 1px solid var(--space-border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      padding: 28px;
      margin-bottom: 24px;
    }
    .card-glow {
      box-shadow: var(--shadow), var(--glow-cyan);
    }
    label {
      display: grid;
      gap: 6px;
      font-size: 0.88rem;
      color: var(--text-muted);
      letter-spacing: 0.03em;
    }
    label .optional {
      font-size: 0.75rem;
      color: rgba(148, 163, 184, 0.7);
    }
    input, select {
      width: 100%;
      border: 1px solid var(--space-border);
      border-radius: 10px;
      padding: 11px 14px;
      font: inherit;
      font-size: 0.95rem;
      color: var(--text-primary);
      background: rgba(5, 5, 16, 0.6);
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    input:focus, select:focus {
      outline: none;
      border-color: var(--accent-cyan);
      box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.15);
    }
    input::placeholder {
      color: rgba(148, 163, 184, 0.5);
    }
    .row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .btn-primary {
      width: 100%;
      border: 0;
      border-radius: 10px;
      padding: 15px 20px;
      font-family: "Orbitron", sans-serif;
      font-size: 0.85rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #050510;
      background: linear-gradient(135deg, var(--accent-cyan) 0%, #06b6d4 100%);
      cursor: pointer;
      box-shadow: var(--glow-cyan);
      transition: transform 0.15s, box-shadow 0.15s;
    }
    .btn-primary:hover {
      transform: translateY(-1px);
      box-shadow: 0 0 30px rgba(34, 211, 238, 0.5);
    }
    .hint {
      margin: 16px 0 0;
      color: var(--text-muted);
      font-size: 0.88rem;
      line-height: 1.6;
    }
    .section-label {
      font-family: "Orbitron", sans-serif;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--accent-purple);
      margin: 0 0 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(168, 85, 247, 0.25);
    }
    .form-section {
      display: grid;
      gap: 14px;
      margin-bottom: 20px;
    }
    .form-section:last-of-type {
      margin-bottom: 24px;
    }
    .mission-list {
      display: grid;
      gap: 12px;
    }
    .mission-card {
      border: 1px solid var(--space-border);
      border-radius: 12px;
      padding: 14px 16px;
      background: rgba(5, 5, 16, 0.5);
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .mission-card:hover {
      border-color: rgba(34, 211, 238, 0.45);
      box-shadow: var(--glow-cyan);
    }
    .mission-card a {
      color: inherit;
      text-decoration: none;
      display: block;
    }
    .mission-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 6px;
      font-weight: 600;
    }
    .mission-meta {
      color: var(--text-muted);
      font-size: 0.85rem;
    }
    .status-badge {
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-family: "Orbitron", sans-serif;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: rgba(34, 211, 238, 0.12);
      color: var(--accent-cyan);
      border: 1px solid rgba(34, 211, 238, 0.3);
      white-space: nowrap;
    }
    .status-badge.completed {
      background: rgba(52, 211, 153, 0.12);
      color: var(--success);
      border-color: rgba(52, 211, 153, 0.3);
    }
    .status-badge.failed {
      background: rgba(248, 113, 113, 0.12);
      color: var(--error);
      border-color: rgba(248, 113, 113, 0.3);
    }
    .status-badge.cancelled {
      background: rgba(148, 163, 184, 0.12);
      color: var(--text-muted);
      border-color: rgba(148, 163, 184, 0.25);
    }
    .status-badge.running, .status-badge.queued {
      background: rgba(168, 85, 247, 0.12);
      color: var(--accent-purple);
      border-color: rgba(168, 85, 247, 0.3);
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 100;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 14px 0;
      margin-bottom: 24px;
      background: rgba(5, 5, 16, 0.75);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--space-border);
    }
    .topbar a {
      color: var(--accent-cyan);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
    .topbar a:hover {
      text-shadow: 0 0 8px rgba(34, 211, 238, 0.6);
    }
    .live-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: var(--text-muted);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-cyan);
      animation: pulse 1.5s ease-in-out infinite;
    }
    .job-status-label {
      font-family: "Orbitron", sans-serif;
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent-purple);
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 20px;
    }
    .stat {
      border: 1px solid var(--space-border);
      border-radius: 12px;
      padding: 14px;
      background: rgba(5, 5, 16, 0.5);
      text-align: center;
    }
    .stat span {
      display: block;
      font-size: 0.72rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }
    .stat strong {
      display: block;
      font-family: "Orbitron", sans-serif;
      font-size: 1.5rem;
      color: var(--accent-cyan);
      text-shadow: var(--glow-cyan);
    }
    .controls {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid var(--space-border);
    }
    .control {
      border: 0;
      border-radius: 10px;
      padding: 12px 20px;
      font-family: "Orbitron", sans-serif;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: pointer;
      transition: opacity 0.2s, box-shadow 0.2s;
    }
    .control.pause {
      color: #050510;
      background: linear-gradient(135deg, var(--accent-cyan) 0%, #06b6d4 100%);
      box-shadow: var(--glow-cyan);
    }
    .control.cancel {
      color: var(--text-primary);
      background: rgba(248, 113, 113, 0.15);
      border: 1px solid rgba(248, 113, 113, 0.4);
    }
    .control.cancel:hover:not(:disabled) {
      background: rgba(248, 113, 113, 0.25);
      box-shadow: 0 0 16px rgba(248, 113, 113, 0.3);
    }
    .control:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }
    .list-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
    }
    .downloads {
      display: grid;
      gap: 12px;
    }
    .download {
      border: 1px solid var(--space-border);
      border-radius: 12px;
      padding: 14px 16px;
      background: rgba(5, 5, 16, 0.45);
    }
    .download-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 10px;
    }
    .download-head strong {
      font-size: 0.92rem;
    }
    .status {
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-family: "Orbitron", sans-serif;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      background: rgba(34, 211, 238, 0.1);
      color: var(--accent-cyan);
      border: 1px solid rgba(34, 211, 238, 0.25);
    }
    .status.completed {
      background: rgba(52, 211, 153, 0.1);
      color: var(--success);
      border-color: rgba(52, 211, 153, 0.3);
    }
    .status.failed {
      background: rgba(248, 113, 113, 0.1);
      color: var(--error);
      border-color: rgba(248, 113, 113, 0.3);
    }
    .status.cancelled {
      background: rgba(148, 163, 184, 0.1);
      color: var(--text-muted);
      border-color: rgba(148, 163, 184, 0.25);
    }
    .status.paused {
      background: rgba(251, 191, 36, 0.1);
      color: var(--warning);
      border-color: rgba(251, 191, 36, 0.3);
    }
    .status.downloading, .status.starting {
      background: rgba(168, 85, 247, 0.1);
      color: var(--accent-purple);
      border-color: rgba(168, 85, 247, 0.3);
    }
    .progress {
      height: 6px;
      border-radius: 999px;
      background: rgba(34, 211, 238, 0.1);
      overflow: hidden;
      margin: 8px 0;
    }
    .bar {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent-cyan) 0%, var(--accent-purple) 100%);
      box-shadow: 0 0 8px rgba(34, 211, 238, 0.6);
      transition: width 0.25s ease;
    }
    .meta {
      color: var(--text-muted);
      font-size: 0.85rem;
    }
    .intro-lede {
      margin: 0 0 28px;
      color: var(--text-muted);
      font-size: 0.95rem;
      line-height: 1.7;
    }
    .intro-lede h1 {
      margin: 0 0 10px;
      font-size: clamp(1.6rem, 4vw, 2.2rem);
      color: var(--text-primary);
      letter-spacing: 0.08em;
    }
    @media (max-width: 640px) {
      .row, .summary {
        grid-template-columns: 1fr;
      }
      .download-head, .topbar, .list-head {
        flex-direction: column;
        align-items: flex-start;
      }
      .site-header .tagline {
        display: none;
      }
    }
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FZbot Mission Control</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Orbitron:wght@600;700&display=swap" rel="stylesheet">
  <style>
{shared_styles}
  </style>
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">FZbot</a>
    <span class="tagline">Mission Control</span>
  </header>

  <main class="shell">
    <div class="intro-lede">
      <h1>Launch Center</h1>
      <p>Configure and deploy a download mission. Track live progress as each transmission completes.</p>
    </div>

    <article class="card card-glow">
      <h2>New Mission</h2>
      <form method="post" action="/jobs">
        <div class="form-section">
          <p class="section-label">Target</p>
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
              Direct URL <span class="optional">optional</span>
              <input name="url" placeholder="mobiletvshows URL">
            </label>
          </div>
        </div>

        <div class="form-section">
          <p class="section-label">Scope</p>
          <div class="row">
            <label>
              Season <span class="optional">optional</span>
              <input type="number" name="season" min="1" placeholder="All seasons">
            </label>
            <label>
              Episode <span class="optional">optional</span>
              <input type="number" name="episode" min="1" placeholder="All episodes">
            </label>
          </div>
          <label>
            Max downloads
            <input type="number" name="max_downloads" min="1" value="10">
          </label>
        </div>

        <div class="form-section">
          <p class="section-label">Engine</p>
          <label>
            Concurrent downloads
            <input type="number" name="concurrent" min="1" max="10" value="3">
          </label>
        </div>

        <button class="btn-primary" type="submit">Launch Mission</button>
      </form>
      <p class="hint">Missions run in the background. You'll be redirected to a live telemetry page once the queue is initialized.</p>
    </article>

    <article class="card">
      <h2>Recent Missions</h2>
      <div class="mission-list">
        {job_items}
      </div>
    </article>
  </main>
</body>
</html>
"""


JOB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | FZbot Mission</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Orbitron:wght@600;700&display=swap" rel="stylesheet">
  <style>
{shared_styles}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(1.4rem, 3.5vw, 2rem);
      color: var(--text-primary);
      letter-spacing: 0.06em;
    }}
    #message {{
      margin: 0;
      color: var(--text-muted);
      font-size: 0.92rem;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <main class="shell wide">
    <div class="topbar">
      <a href="/">&larr; Mission Control</a>
      <div class="live-indicator">
        <span class="live-dot"></span>
        <span>Live</span>
      </div>
      <div class="job-status-label" id="job-state">{status_label}</div>
    </div>

    <section class="card card-glow">
      <h1>{title}</h1>
      <p id="message">{message}</p>
      <div class="summary">
        <div class="stat"><span>Total</span><strong id="count-total">0</strong></div>
        <div class="stat"><span>Completed</span><strong id="count-completed">0</strong></div>
        <div class="stat"><span>Active</span><strong id="count-active">0</strong></div>
        <div class="stat"><span>Failed</span><strong id="count-failed">0</strong></div>
      </div>
      <div class="controls">
        <button id="pause-button" class="control pause" type="button">Pause</button>
        <button id="cancel-button" class="control cancel" type="button">Abort Mission</button>
      </div>
    </section>

    <section class="card">
      <div class="list-head">
        <h2>Transmission Log</h2>
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
      document.title = `${{data.title}} | FZbot Mission`;
      document.getElementById("job-state").textContent = data.status;
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
        root.innerHTML = `<div class="download"><div class="meta">Initializing transmission queue&hellip;</div></div>`;
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
            ${{item.detail ? ` &bull; ${{item.detail}}` : ""}}
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
        document.getElementById("message").textContent = `Abort failed: ${{error.message}}`;
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
        document.getElementById("message").textContent = `Telemetry link lost: ${{error.message}}`;
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
        status_class = job.status.replace(" ", "_")
        job_items.append(
            """
            <article class="mission-card">
              <a href="/jobs/{job_id}">
                <div class="mission-head">
                  <span>{title}</span>
                  <span class="status-badge {status_class}">{status}</span>
                </div>
                <div class="mission-meta">S{season} &bull; E{episode} &bull; {concurrent} threads</div>
              </a>
            </article>
            """.format(
                job_id=job.job_id,
                title=job.title,
                status=job.status,
                status_class=status_class,
                season=job.season or "all",
                episode=job.episode or "all",
                concurrent=job.concurrent,
            )
        )
    if not job_items:
        job_items.append(
            '<div class="mission-card"><div class="mission-meta">No missions yet. Configure and launch one above.</div></div>'
        )
    return INDEX_HTML.format(shared_styles=SHARED_STYLES, job_items="".join(job_items))


def _render_job(job: BrowserJob) -> str:
    return JOB_HTML.format(
        shared_styles=SHARED_STYLES,
        title=job.title,
        message=job.message,
        status_label=job.status,
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
