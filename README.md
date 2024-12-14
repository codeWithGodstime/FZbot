# FZBot Downloader

###### Effortlessly download films and TV shows directly from the web using a powerful and user-friendly terminal-based tool.

FZBot Downloader helps you effortlessly download films and TV shows directly from the web using a powerful and user-friendly terminal-based tool.

### Key Features

- Download movies and TV shows with minimal input. 

- Automatic URL parsing to simplify the download process. 

- Resume interrupted downloads seamlessly. Lightweight and cross-platform support (Windows, macOS, Linux).

- Concurrent downloads

### Demo

![Live Demo](https://taskmaster-demo.com)

### Installation

- Clone the repository
  
  ```bash
  git clone https://github.com/codeWithGodstime/FZbot
  ```

- Create virtual environment and install dependencies
  
  ```bash
  cd FZbot && virtualenv venv && pip install -r requirements.txt
  ```

### Usage

Basic Usage

```bash
python fzbot.py [type] [title] [-ns NUMBER_OF_SEASONS] [-ne NUMBER_OF_EPISODES]
```

### Arguments:

1. **Positional Arguments** (Required):
   
   - **`type`**: Specify whether you want to download a movie or a series.
     - Choices: `movie`, `series`
     - Example: `movie` for films or `series` for TV shows.
   - **`title`**: Name of the movie or series you want to download.
     - Example: `"Breaking Bad"` or `"Inception"`

2. **Optional Arguments** (Optional):
   
   - **`-ns`, `--number_of_seasons`**:
     
     - Specify the number of seasons to download (for series only).
     - Default: `1`
     - Example: `--number_of_seasons 2` to download 2 seasons.
   
   - **`-ne`, `--number_of_episodes`**:
     
     - Specify the number of episodes to download (for series only).
     - Default: `1`
     - Example: `--number_of_episodes 5` to download 5 episodes.

Here's a clear and structured usage guide based on your `argparse` implementation:

---

## Usage Guide for **FZBot Downloader**

**FZBot Downloader** is a terminal-based tool for downloading movies or TV series. Use the following commands and arguments to get started:

---

### Basic Command Structure:

bash

Copy code

`python fzbot.py [type] [title] [-ns NUMBER_OF_SEASONS] [-ne NUMBER_OF_EPISODES]`

---

### Arguments:

1. **Positional Arguments** (Required):
   
   - **`type`**: Specify whether you want to download a movie or a series.
     - Choices: `movie`, `series`
     - Example: `movie` for films or `series` for TV shows.
   - **`title`**: Name of the movie or series you want to download.
     - Example: `"Breaking Bad"` or `"Inception"`

2. **Optional Arguments** (Optional):
   
   - **`-ns`, `--number_of_seasons`**:
     
     - Specify the number of seasons to download (for series only).
     - Default: `1`
     - Example: `--number_of_seasons 2` to download 2 seasons.
   
   - **`-ne`, `--number_of_episodes`**:
     
     - Specify the number of episodes to download (for series only).
     - Default: `1`
     - Example: `--number_of_episodes 5` to download 5 episodes.

---

### Examples:

1. **Download a Movie**:
   
   ```bash
   python fzbot.py movie "Inception"
   ```

2. **Download a TV Series (Default 1 season, 1 episode)**:
   
   ```bash
   python fzbot.py series "Breaking Bad"
   ```

3. **Download Multiple Seasons of a TV Series**:
   
   ```bash
   python fzbot.py series "Breaking Bad" -ns 2
   ```

4. **Download Multiple Episodes of a TV Series**:
   
   ```bash
   python fzbot.py series "Breaking Bad" -ns 1 -ne 10
   ```
   
   
