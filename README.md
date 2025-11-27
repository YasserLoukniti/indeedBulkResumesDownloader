# Indeed CV Downloader

**Version 2.3.0**

Automated tool to bulk download resumes from Indeed Employer platform.

## Features

### Core Features
- Automatic bulk CV/resume download
- Session-based authentication (no credentials needed)
- Smart resume on interruption with checkpoint system
- **Smart skip**: Automatically skips already downloaded candidates
- Progress tracking with real-time statistics
- Configurable delays and parameters
- Automatic file naming with candidate names
- Bilingual support (English / French)

### Multi-Job Manager (v2.1)
- **All jobs at once**: Fetch and process all jobs from Indeed Employer dashboard
- **HTML table parsing**: Reliable extraction via pagination buttons
- **Smart comparison**: Compare jobs with existing download folders
- **New candidates detection**: Only download new CVs since last run
- **Clean folder names**: Removes H/F variants, replaces `/` with `-`
- **Status filter**: Filter by Open, Paused, or Closed jobs
- **Backend/Frontend modes**: API (fast) or Selenium (stable)

## Prerequisites

- Google Chrome browser
- Indeed Employer account with access to candidates
- Active Indeed Employer session

## Standalone Executables (No Python Required)

Pre-built executables are available in the `dist/` folder:

| File                     | Description                 |
| ------------------------ | --------------------------- |
| `IndeedCVDownloader.exe` | Main downloader application |
| `ConvertCookies.exe`     | Cookie format converter     |

### Quick Start (Executable)

1. Export your cookies from Chrome (see "Export your Indeed cookies" below)
2. Save the file as `logs/indeed_cookies.txt`
3. Run `ConvertCookies.exe` to convert to JSON format
4. Run `IndeedCVDownloader.exe`
5. Choose your options in the menu

## Installation (Python)

### 1. Clone the repository

```bash
git clone https://github.com/YasserLoukniti/indeed-cv-downloader.git
cd indeed-cv-downloader
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Export your Indeed cookies

**Method 1: Using Browser Extension (Recommended)**

1. Install "Get cookies.txt" Chrome extension
2. Navigate to `https://employers.indeed.com/candidates`
3. Click the extension icon and export cookies
4. Save as `logs/indeed_cookies.txt`

**Method 2: Using Console**

1. Open Indeed Employer in Chrome
2. Press F12 → Console tab
3. Paste and run the export script (see GUIDE_COOKIES.md)
4. Save output to a file

### 4. Convert cookies to JSON

```bash
python convert_cookies.py
```

This will read `logs/indeed_cookies.txt` and create `logs/indeed_cookies.json`.

## Usage

### Run the main script

```bash
python indeed_downloader.py
```

### Menu Options

1. **Download Mode**:
   - `Backend (API)` - Faster, parallel downloads via GraphQL
   - `Frontend (Selenium)` - More stable, simulates clicks

2. **Job Selection**:
   - `Single job` - Navigate to a specific job manually
   - `All jobs` - Process all jobs automatically

3. **Status Filter** (for All jobs mode):
   - Open only
   - Paused only
   - Closed only
   - Open + Paused
   - All statuses

### Example Output

```
Recuperation de la liste des jobs...
   URL: https://employers.indeed.com/jobs?status=open,paused,closed
   Page 1...
      25 jobs sur cette page (total: 25)
   Page 2...
      25 jobs sur cette page (total: 50)
   ...

145 jobs recuperes

Liste des jobs:
------------------------------------------------------------
     1. [O] Business Developer
        Date: 22-09-2025 | Candidats: 237
     2. [P] Data Scientist
        Date: 01-07-2025 | Candidats: 550
     3. [F] Marketing Manager
        Date: 15-06-2025 | Candidats: 120
------------------------------------------------------------

JOBS DEJA PRESENTS DANS LE DOSSIER DOWNLOADS:
============================================================
   [NEW] Data Scientist
         450 CVs telecharges / 550 candidats (+100 nouveaux)
   [OK]  Marketing Manager (120 CVs)

Options:
   [S] SkipAll - Ignorer TOUS les jobs existants
   [N] NewOnly - Telecharger seulement les jobs avec nouveaux candidats
   [K] KeepAll - Telecharger quand meme tous les jobs
```

## Configuration

Edit `.env.config` to customize parameters:

```bash
# Download speeds
DOWNLOAD_DELAY=0.5              # Delay after clicking download button
NEXT_CANDIDATE_DELAY=1.0        # Delay after navigating to next candidate

# Download limit
MAX_CVS=3000                    # Number of CVs to download per job

# Directories
DOWNLOAD_FOLDER=downloads       # CV download directory
LOG_FOLDER=logs                 # Logs and checkpoints directory
```

## Resume from Interruption

If the script stops (Ctrl+C, error, or internet issue):

1. Simply re-run the script
2. It automatically resumes from the last checkpoint
3. Already downloaded CVs are skipped

To start fresh:

```bash
del logs\checkpoint_unified.json
```

## File Structure

```
indeed-cv-downloader/
├── dist/                       # Standalone executables
│   ├── IndeedCVDownloader.exe  # Main application
│   └── ConvertCookies.exe      # Cookie converter
├── indeed_downloader.py        # Main unified script
├── convert_cookies.py          # Cookie converter utility
├── requirements.txt            # Python dependencies
├── .env.config                 # Configuration file
├── downloads/                  # Downloaded CVs organized by job
│   ├── Job Title (DD-MM-YYYY)/
│   │   ├── Candidate_Name_timestamp.pdf
│   │   └── checkpoint.json
│   └── ...
└── logs/                       # Logs and checkpoints
    ├── checkpoint_unified.json # Global resume state
    ├── indeed_cookies.txt      # Exported cookies (Netscape)
    └── indeed_cookies.json     # Converted cookies (JSON)
```

## Troubleshooting

### Cookies expired
Re-export cookies from your browser and run `convert_cookies.py` again.

### Chrome profile error
Close all Chrome windows before running the script.

### Missing jobs in list
The script now uses HTML table pagination. If some jobs are missing, check if the page loaded correctly.

### Download verification failed
Increase `DOWNLOAD_DELAY` in `.env.config`.

## Important Notes

- Uses your active browser session (no password storage)
- Cookies expire after ~24 hours, re-export when needed
- All downloaded CVs are saved with timestamps
- Checkpoint system ensures no duplicates

## Legal & Ethics

- For personal use only
- Respect Indeed's Terms of Service
- Only download CVs you have legitimate access to
- Handle candidate data responsibly per GDPR/privacy laws

## License

MIT License - See LICENSE file for details

## Contributing

Pull requests welcome. For major changes, open an issue first.

## Support

For issues or questions, open a GitHub issue with:
- Error message from logs
- Configuration used
- Steps to reproduce

---

## Changelog

### v2.3.0 (2025-11-27)

**New Features:**
- **Auto-close modals**: Automatically closes popups/modals when navigating to jobs
- **Better folder matching**: Normalized comparison (removes accents, special chars) for matching job names with existing folders

**Improvements:**
- Partial name matching for existing folders (if one name contains the other)
- Press ESC key to close any remaining modals

### v2.2.0 (2025-11-27)

**New Features:**
- **Multi-pass fetch to bypass Indeed's 3000 limit**: Fetches candidates using multiple sort strategies (date ASC/DESC, name ASC/DESC) to recover up to ~12000 candidates
- **Smart existing folder detection**: Scans existing PDF files to detect already downloaded candidates even without checkpoint
- **Per-job checkpoint**: Each job folder has its own `checkpoint.json` for accurate tracking

**Improvements:**
- 5 passes to maximize candidate recovery:
  - Pass 1: Sort by date (oldest first)
  - Pass 2: Sort by date (newest first)
  - Pass 3: Sort by name (A to Z)
  - Pass 4: Sort by name (Z to A)
  - Pass 5: By individual disposition status (if >1000 still missing)
- Shows percentage of candidates recovered when API limit is hit
- Better deduplication using legacy_id

### v2.1.0 (2025-11-27)

**New Features:**
- Unified script `indeed_downloader.py` replaces all previous scripts
- Interactive menu for mode selection (Backend/Frontend, Single/All jobs)
- HTML table parsing with pagination for reliable job fetching
- Status filter in URL (`open`, `paused`, `closed`)
- Display all jobs with cleaned names after fetching
- New option `[N] NewOnly` to download only jobs with new candidates

**Improvements:**
- Clean job titles: removes `(H/F)`, `H/F`, replaces `/` with `-`
- Better folder matching with cleaned names
- Shows CV count vs total candidates for existing folders
- Improved pagination with scroll and wait times

**Removed:**
- `indeed_jobs_manager.py` (merged into main script)
- `indeed_parallel.py` (merged into main script)
- `indeed_with_cookies.py` (merged into main script)
- `capture_requests.py` (debug script)

### v2.0.0 (2025-11-27)

**New Features:**
- Multi-job management system
- Compare jobs with existing download folders
- Detect new candidates since last download
- Organize downloads by job folder

### v1.1.0 (2025-11-20)

**New Features:**
- Parallel download via GraphQL API
- Automatic header capture from network requests

### v1.0.0 (2025-11-15)

**Initial Release:**
- Cookie-based authentication
- Checkpoint system for resume on interruption
- Smart skip for already downloaded candidates
- Standalone executables
