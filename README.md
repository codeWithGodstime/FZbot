# FZBot Downloader

## Effortlessly download films and TV shows directly from the web using a powerful and user-friendly terminal-based tool.

FZBot Downloader helps you effortlessly download films and TV shows directly from the web from your terminal.

### Key Features

- Download movies and TV shows with minimal input.
- Automatic URL parsing to simplify the download process.
- Resume interrupted downloads seamlessly. Lightweight and cross-platform support (Windows, macOS, Linux).
- Concurrent downloads
- Local web UI mode (`fzbot ui`)

### Installation

```bash
git clone https://github.com/codeWithGodstime/FZbot
cd FZbot
pip install -e .
```

### Usage

Downloads are saved to `~/Videos/fzbot/<title>/` by default (or `~/Movies/fzbot/` on macOS). Use `--output` to override.

```bash
fzbot movie "Inception"
fzbot series "Breaking Bad" --season 2 --episode 10
fzbot movie "Inception" --output /mnt/media/downloads
fzbot ui --port 8080
```

### Arguments

1. **Positional Arguments** (Required):
   - **`type`**: Specify whether you want to download a movie or a series.
     - Choices: `movie`, `series`
   - **`title`**: Name of the movie or series you want to download.

2. **Optional Arguments**:
   - **`--season`**: Specify the season to download (for series only).
   - **`--episode`**: Specify a single episode to download (for series only).
   - **`--max_downloads`**: Limit the number of episodes or movies to download (default: 10).
   - **`--concurrent`**: Number of concurrent downloads (default: 3).
   - **`--output`**: Directory to save downloads (default: `~/Videos/fzbot`).
   - **`--url`**: Direct URL for a single movie or series.

### Examples

1. **Download a Movie**:

   ```bash
   fzbot movie "Inception"
   ```

2. **Download a TV Series**:

   ```bash
   fzbot series "Breaking Bad"
   ```

3. **Download a Specific Season**:

   ```bash
   fzbot series "Breaking Bad" --season 2
   ```

4. **Download a Specific Episode**:

   ```bash
   fzbot series "Breaking Bad" --season 1 --episode 10
   ```

5. **Run the Web UI**:

   ```bash
   fzbot ui
   ```
