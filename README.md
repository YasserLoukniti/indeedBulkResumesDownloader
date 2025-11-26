# Indeed CV Downloader

Automated tool to bulk download resumes from Indeed Employer platform.

## Features

- Automatic bulk CV/resume download
- Session-based authentication (no credentials needed)
- Smart resume on interruption with checkpoint system
- **Smart skip**: Automatically skips already downloaded candidates in batch
- Progress tracking with real-time statistics and time tracking
- Configurable delays and parameters
- Automatic file naming with candidate names
- Bilingual support (English "Download resume" / French "Télécharger le CV")
- Error handling and retry logic

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
4. Open Indeed Employer in Chrome and navigate to your candidates list
5. Run `IndeedCVDownloader.exe`
6. Click on the first candidate you want to download, then press Enter

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
4. Save as `employers.indeed.com_cookies.txt` in project folder

**Method 2: Using Console**

1. Open Indeed Employer in Chrome
2. Press F12 → Console tab
3. Paste and run the export script (see GUIDE_COOKIES.md)
4. Save output to a file

### 4. Convert cookies to JSON

1. Save your exported cookies as `logs/indeed_cookies.txt`
2. Run the converter:

```bash
python convert_cookies.py
```

This will read `logs/indeed_cookies.txt` and create `logs/indeed_cookies.json`.

## Configuration

Edit `.env.config` to customize parameters:

```bash
# Download speeds
DOWNLOAD_DELAY=0.5              # Delay after clicking download button (seconds)
NEXT_CANDIDATE_DELAY=1.0        # Delay after navigating to next candidate
BETWEEN_CANDIDATES_DELAY=0.5    # Delay between each candidate
PAGE_LOAD_DELAY=5               # Initial page load wait time

# Download limit
MAX_CVS=10                      # Number of CVs to download (set to 3000 for all)

# Timeouts
DOWNLOAD_VERIFY_TIMEOUT=30      # Timeout for download verification

# Directories
DOWNLOAD_FOLDER=downloads       # CV download directory
LOG_FOLDER=logs                 # Logs and checkpoints directory
```

### Performance Presets

**Ultra-Fast** (~2s per CV, ~1h40 for 3000 CVs)

```
DOWNLOAD_DELAY=0.5
NEXT_CANDIDATE_DELAY=1.0
BETWEEN_CANDIDATES_DELAY=0.5
```

**Stable** (~4s per CV, ~3h20 for 3000 CVs) - Recommended

```
DOWNLOAD_DELAY=1.0
NEXT_CANDIDATE_DELAY=1.5
BETWEEN_CANDIDATES_DELAY=1.0
```

**Safe** (~8s per CV, ~6h40 for 3000 CVs)

```
DOWNLOAD_DELAY=2.0
NEXT_CANDIDATE_DELAY=3.0
BETWEEN_CANDIDATES_DELAY=2.0
```

## Usage

### 1. Close Chrome completely

Ensure all Chrome windows are closed before running the script.

### 2. Run the script

```bash
python indeed_with_cookies.py
```

### 3. Follow the prompts

1. Open Indeed Employer in Chrome and go to your candidates list
2. Run the script - it opens Chrome with your saved cookies
3. **Click on the first candidate** you want to download
4. Press Enter to start automatic download
5. Script downloads CVs and navigates automatically through the list

### 4. Monitor progress

```
CVs: 150it [25:30, 10.20s/it]

============================================================
📊 STATISTIQUES
============================================================
Total:      150
✅ Réussis:  145
❌ Échecs:   3
⏭️ Ignorés:  2
Taux:       96.67%

⏱️ Temps total: 0h 25m 30s
⏱️ Moyenne/CV:  10.6s
============================================================
```

## Resume from Interruption

If the script stops (Ctrl+C, error, or internet issue):

1. Simply re-run the script
2. It automatically resumes from the last checkpoint
3. Already downloaded CVs are skipped

To start fresh:

```bash
del logs\checkpoint.json
```

## File Structure

```
indeed-cv-downloader/
├── dist/                       # Standalone executables
│   ├── IndeedCVDownloader.exe  # Main application (no Python needed)
│   └── ConvertCookies.exe      # Cookie converter (no Python needed)
├── indeed_with_cookies.py      # Main script (Python version)
├── convert_cookies.py          # Cookie converter utility (Python version)
├── requirements.txt            # Python dependencies
├── .env.config                 # Configuration file
├── .gitignore                  # Git ignore rules
├── downloads/                  # Downloaded CVs (PDF format)
│   └── Candidate_Name_YYYYMMDD_HHMMSS.pdf
└── logs/                       # Logs and checkpoints
    ├── checkpoint.json         # Resume state
    ├── indeed_cookies.txt      # Exported cookies (Netscape format)
    ├── indeed_cookies.json     # Converted cookies (JSON format)
    └── scraper_*.log          # Execution logs
```

## Troubleshooting

### Cookies expired

Re-export cookies from your browser and run `convert_cookies.py` again.

### Chrome profile error

The script uses a clean Chrome session. Close all Chrome windows before running.

### Download verification failed

Increase `DOWNLOAD_DELAY` in `.env.config` to give more time for PDFs to download.

### No candidates found

Ensure you're on the correct Indeed Employer URL and have candidates in your list.

## Important Notes

- Uses your active browser session (no password storage)
- Cookies expire after ~24 hours, re-export when needed
- Rate limiting prevents Indeed from blocking your IP
- All downloaded CVs are saved with timestamps
- Checkpoint system ensures no duplicates

## Performance Tips

1. **Test first**: Run with `MAX_CVS=10` before bulk download
2. **Stable connection**: Use ethernet, not WiFi
3. **Overnight runs**: For large batches (1000+ CVs)
4. **Monitor logs**: Check `logs/` folder for issues

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
