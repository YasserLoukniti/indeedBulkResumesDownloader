"""
Indeed CV Downloader - Unified Script
Supports both Backend (API parallel) and Frontend (Selenium clicks) modes
Can process single job or all jobs automatically
"""

import os
import sys
import json
import time
import re
import base64
from urllib.parse import urlparse, parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import chromedriver_autoinstaller
from tqdm import tqdm

# Load environment variables
load_dotenv('.env.config')


class IndeedDownloader:
    def __init__(self):
        # Config from .env
        self.download_folder = os.getenv('DOWNLOAD_FOLDER', 'downloads')
        self.log_folder = os.getenv('LOG_FOLDER', 'logs')
        self.max_cvs = int(os.getenv('MAX_CVS', 3000))
        self.parallel_downloads = int(os.getenv('PARALLEL_DOWNLOADS', 10))
        self.download_delay = float(os.getenv('DOWNLOAD_DELAY', 0.5))
        self.next_candidate_delay = float(os.getenv('NEXT_CANDIDATE_DELAY', 1.0))

        # Create folders
        Path(self.download_folder).mkdir(exist_ok=True)
        Path(self.log_folder).mkdir(exist_ok=True)

        # Session state
        self.driver = None
        self.wait = None
        self.api_key = None
        self.ctk = None
        self.cookies = {}

        # Current job info
        self.current_job_id = None
        self.current_job_name = None
        self.current_job_folder = None
        self.current_job_is_existing = False  # True if job folder already existed

        # Checkpoint
        self.checkpoint_file = Path(self.log_folder) / 'checkpoint_unified.json'
        self.checkpoint_data = self._load_checkpoint()

        # Stats
        self.stats = {
            'total_processed': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'archived': 0  # Jobs with no candidates (too old/archived)
        }
        self.start_time = None

        # Mode settings
        self.mode = None  # 'backend' or 'frontend'
        self.job_mode = None  # 'single' or 'all'
        self.job_statuses = []  # ['ACTIVE', 'PAUSED', 'CLOSED']

    def _load_checkpoint(self) -> dict:
        """Load checkpoint data"""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'downloaded_names': [],
            'downloaded_ids': [],
            'completed_jobs': []
        }

    def _save_checkpoint(self, name: str = None, legacy_id: str = None, job_id: str = None):
        """Save checkpoint"""
        if name and name not in self.checkpoint_data['downloaded_names']:
            self.checkpoint_data['downloaded_names'].append(name)
        if legacy_id and legacy_id not in self.checkpoint_data['downloaded_ids']:
            self.checkpoint_data['downloaded_ids'].append(legacy_id)
        if job_id and job_id not in self.checkpoint_data['completed_jobs']:
            self.checkpoint_data['completed_jobs'].append(job_id)

        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.checkpoint_data, f, ensure_ascii=False, indent=2)

    def show_menu(self):
        """Display main menu and get user choices"""
        print("""
╔════════════════════════════════════════════════════════════╗
║         Indeed CV Downloader - Version Unifiée             ║
╚════════════════════════════════════════════════════════════╝
""")

        # Mode selection
        print("📥 MODE DE TÉLÉCHARGEMENT:")
        print("   1. Backend (API) - Plus rapide, téléchargements parallèles")
        print("   2. Frontend (Selenium) - Plus stable, clics simulés")
        print()

        while True:
            choice = input("Choix (1/2): ").strip()
            if choice == '1':
                self.mode = 'backend'
                break
            elif choice == '2':
                self.mode = 'frontend'
                break
            print("❌ Choix invalide")

        print()

        # Job mode selection
        print("📋 MODE DE SÉLECTION DES JOBS:")
        print("   1. Job unique - Vous naviguez vers le job souhaité")
        print("   2. Tous les jobs - Parcourt automatiquement tous les jobs")
        print()

        while True:
            choice = input("Choix (1/2): ").strip()
            if choice == '1':
                self.job_mode = 'single'
                break
            elif choice == '2':
                self.job_mode = 'all'
                break
            print("❌ Choix invalide")

        # Status filter (only for 'all' mode)
        if self.job_mode == 'all':
            print()
            print("📊 STATUT DES ANNONCES À TRAITER:")
            print("   1. Ouvertes uniquement (ACTIVE)")
            print("   2. Suspendues uniquement (PAUSED)")
            print("   3. Fermées uniquement (CLOSED)")
            print("   4. Ouvertes + Suspendues")
            print("   5. Toutes (Ouvertes + Suspendues + Fermées)")
            print()

            while True:
                choice = input("Choix (1-5): ").strip()
                if choice == '1':
                    self.job_statuses = ['ACTIVE']
                    break
                elif choice == '2':
                    self.job_statuses = ['PAUSED']
                    break
                elif choice == '3':
                    self.job_statuses = ['CLOSED']
                    break
                elif choice == '4':
                    self.job_statuses = ['ACTIVE', 'PAUSED']
                    break
                elif choice == '5':
                    self.job_statuses = ['ACTIVE', 'PAUSED', 'CLOSED']
                    break
                print("❌ Choix invalide")

        print()
        print("=" * 60)
        print(f"✅ Mode: {self.mode.upper()}")
        print(f"✅ Jobs: {'Unique' if self.job_mode == 'single' else 'Tous'}")
        if self.job_mode == 'all':
            print(f"✅ Statuts: {', '.join(self.job_statuses)}")
        print("=" * 60)
        print()

    def setup_chrome(self) -> bool:
        """Setup Chrome with cookies"""
        print("🌐 Ouverture de Chrome...")

        # Load cookies
        cookies_file = Path(self.log_folder) / 'indeed_cookies.json'
        if not cookies_file.exists():
            print(f"❌ Fichier cookies non trouvé: {cookies_file}")
            return False

        with open(cookies_file, 'r', encoding='utf-8') as f:
            cookies_list = json.load(f)

        # Install chromedriver
        chromedriver_autoinstaller.install()

        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--log-level=3')  # Suppress Chrome logs
        chrome_options.add_argument('--silent')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        # Download preferences
        prefs = {
            "download.default_directory": str(Path(self.download_folder).absolute()),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 30)

        # Go to Indeed and add cookies
        print("✅ Création d'une session avec vos cookies")
        self.driver.get("https://employers.indeed.com")
        time.sleep(2)

        for cookie in cookies_list:
            try:
                cookie_dict = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie.get('domain', '.indeed.com'),
                    'path': cookie.get('path', '/')
                }
                self.driver.add_cookie(cookie_dict)
                self.cookies[cookie['name']] = cookie['value']

                if cookie['name'] == 'CTK':
                    self.ctk = cookie['value']
            except:
                pass

        self.driver.refresh()
        time.sleep(3)

        # Capture API key from network logs
        self._capture_api_key()

        print(f"✅ {len(cookies_list)} cookies chargés")
        return True

    def _capture_api_key(self):
        """Capture API key from network logs"""
        try:
            # Navigate to candidates to trigger API calls
            self.driver.get("https://employers.indeed.com/candidates")
            time.sleep(5)

            logs = self.driver.get_log('performance')
            for log in logs:
                try:
                    message = json.loads(log['message'])['message']
                    if message['method'] == 'Network.requestWillBeSent':
                        url = message['params']['request']['url']
                        if 'graphql' in url and 'apis.indeed.com' in url:
                            headers = message['params']['request']['headers']
                            if 'indeed-api-key' in headers:
                                self.api_key = headers['indeed-api-key']
                                break
                except:
                    continue

            if self.api_key:
                print(f"   ✅ API Key capturée")
        except:
            pass

    def _clean_job_title(self, title: str) -> str:
        """Nettoie le titre du job pour créer un nom de dossier valide"""
        # Enlever (H/F), H/F, (F/H), F/H et variantes
        title = re.sub(r'\s*\(?\s*[HF]\s*/\s*[HF]\s*\)?\s*', '', title, flags=re.IGNORECASE)
        # Remplacer / par -
        title = title.replace('/', '-')
        # Enlever les caractères invalides pour un nom de dossier Windows
        title = re.sub(r'[<>:"|?*]', '', title)
        # Enlever les espaces multiples
        title = re.sub(r'\s+', ' ', title)
        # Trim
        title = title.strip()
        return title

    def _create_job_folder(self, job_name: str, job_date: str = None) -> Path:
        """Create folder for job with name and date"""
        # Clean job name for folder
        safe_name = self._clean_job_title(job_name)
        safe_name = safe_name[:80]  # Limit length

        if job_date:
            folder_name = f"{safe_name} ({job_date})"
        else:
            folder_name = safe_name

        job_folder = Path(self.download_folder) / folder_name

        # Check if folder already exists (has PDFs)
        self.current_job_is_existing = job_folder.exists() and any(job_folder.glob('*.pdf'))

        job_folder.mkdir(exist_ok=True)

        self.current_job_folder = job_folder
        return job_folder

    def _close_modals(self):
        """Close any modal/popup that might be open"""
        try:
            # Common modal close selectors
            close_selectors = [
                "button[aria-label='Close']",
                "button[aria-label='Fermer']",
                "button[data-testid='modal-close']",
                "button[data-testid='CloseButton']",
                "[data-testid='modal-close-button']",
                ".modal-close",
                ".close-modal",
                "button.css-1k9jcwk",  # Indeed's close button class
                "[aria-label='close']",
                "[aria-label='dismiss']",
                "button[class*='close']",
                "div[role='dialog'] button[type='button']",
            ]

            for selector in close_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for btn in buttons:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(0.3)
                except:
                    continue

            # Also try pressing Escape key
            try:
                from selenium.webdriver.common.keys import Keys
                body = self.driver.find_element(By.TAG_NAME, "body")
                body.send_keys(Keys.ESCAPE)
                time.sleep(0.3)
            except:
                pass

        except:
            pass

    def _extract_job_id_from_url(self, url: str) -> Optional[str]:
        """Extract employerJobId from URL"""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'selectedJobs' in params:
                return unquote(params['selectedJobs'][0])
        except:
            pass
        return None

    # ==================== BACKEND MODE (API) ====================

    def fetch_candidates_api(self, offset: int = 0, limit: int = 100, dispositions: list = None, sort_by: str = "APPLY_DATE", sort_order: str = "DESCENDING"):
        """Fetch candidates using GraphQL API via browser"""
        query = """query FindRCPMatches($input: OrchestrationMatchesInput!) {
  findRCPMatches(input: $input) {
    overallMatchCount
    matchConnection {
      pageInfo { hasNextPage }
      matches {
        candidateSubmission {
          id
          data {
            profile { name { displayName } }
            resume {
              ... on CandidatePdfResume { id, downloadUrl }
            }
            ... on IndeedApplyCandidateSubmission { legacyID }
            ... on EmployerGeneratedCandidateSubmission { legacyID }
          }
        }
      }
    }
  }
}"""

        if dispositions is None:
            dispositions = ["NEW", "PENDING", "PHONE_SCREENED", "INTERVIEWED", "OFFER_MADE", "REVIEWED"]

        surface_context = [{"contextKey": "DISPOSITION", "contextPayload": d} for d in dispositions]
        surface_context.append({"contextKey": "SORT_BY", "contextPayload": sort_by})
        surface_context.append({"contextKey": "SORT_ORDER", "contextPayload": sort_order})

        variables = {
            "input": {
                "clientSurfaceName": "candidate-list-page",
                "defaultStrategyId": "U20GF",
                "limit": limit,
                "offset": offset,
                "context": {
                    "surfaceContext": surface_context
                },
                "searchSessionId": f"dl-{int(time.time())}-{offset}"
            }
        }

        if self.current_job_id:
            variables["input"]["identifiers"] = {
                "jobIdentifiers": {"employerJobId": self.current_job_id}
            }

        payload = {"operationName": "FindRCPMatches", "variables": variables, "query": query}

        js_code = f"""
        return await fetch("https://apis.indeed.com/graphql?co=FR&locale=fr-FR", {{
            method: "POST",
            headers: {{
                "accept": "*/*",
                "content-type": "application/json",
                "indeed-api-key": "{self.api_key}",
                "indeed-ctk": "{self.ctk}",
                "indeed-client-sub-app": "talent-organization-modules",
                "indeed-client-sub-app-component": "./CandidateListPage"
            }},
            body: JSON.stringify({json.dumps(payload)}),
            credentials: "include"
        }}).then(r => r.json());
        """

        try:
            result = self.driver.execute_script(js_code)
            if not result or 'errors' in result:
                return [], 0

            matches = result.get('data', {}).get('findRCPMatches', {}).get('matchConnection', {}).get('matches', [])
            total = result.get('data', {}).get('findRCPMatches', {}).get('overallMatchCount', 0)
            return matches, total
        except Exception as e:
            print(f"❌ Erreur API: {e}")
            return [], 0

    def download_cv_api(self, candidate: dict) -> bool:
        """Download CV via API"""
        name = candidate['name']
        legacy_id = candidate['legacy_id']
        download_url = candidate['download_url']

        if legacy_id in self.checkpoint_data['downloaded_ids']:
            self.stats['skipped'] += 1
            return True

        try:
            js_code = f"""
            const response = await fetch("{download_url}", {{ credentials: "include" }});
            if (!response.ok) {{
                const altResponse = await fetch("https://employers.indeed.com/api/catws/resume/v2/download?id={legacy_id}", {{ credentials: "include" }});
                if (!altResponse.ok) return null;
                const blob = await altResponse.blob();
                return await new Promise((resolve) => {{
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.readAsDataURL(blob);
                }});
            }}
            const blob = await response.blob();
            return await new Promise((resolve) => {{
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                reader.readAsDataURL(blob);
            }});
            """

            base64_data = self.driver.execute_script(js_code)
            if not base64_data:
                self.stats['failed'] += 1
                return False

            pdf_data = base64.b64decode(base64_data)

            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_name}_{timestamp}.pdf"

            folder = self.current_job_folder or Path(self.download_folder)
            filepath = folder / filename

            with open(filepath, 'wb') as f:
                f.write(pdf_data)

            if filepath.stat().st_size > 1000:
                self._save_checkpoint(name=name, legacy_id=legacy_id)
                self.stats['downloaded'] += 1
                return True
            else:
                filepath.unlink()
                self.stats['failed'] += 1
                return False

        except Exception as e:
            self.stats['failed'] += 1
            return False

    def run_backend_single_job(self):
        """Run backend mode for single job"""
        print("\n" + "=" * 60)
        print("👆 Naviguez vers le job souhaité dans Chrome")
        print("   puis appuyez sur Entrée")
        print("=" * 60)
        input()

        job_url = self.driver.current_url
        self.current_job_id = self._extract_job_id_from_url(job_url)

        # Get job name from page
        try:
            job_name = self.driver.execute_script("""
                const el = document.querySelector('[data-testid="job-title"]') ||
                           document.querySelector('h1') ||
                           document.querySelector('.job-title');
                return el ? el.textContent.trim() : 'Job';
            """)
            self._create_job_folder(job_name)
            print(f"📁 Dossier: {self.current_job_folder}")
        except:
            pass

        self._download_all_candidates_api()

    def _load_job_checkpoint(self, scan_pdfs: bool = False) -> tuple:
        """Load checkpoint for current job folder - returns (downloaded_ids, downloaded_names)

        Args:
            scan_pdfs: If True, scan existing PDF files for names (for existing jobs with new candidates)
        """
        downloaded_ids = set(self.checkpoint_data.get('downloaded_ids', []))
        downloaded_names = set(self.checkpoint_data.get('downloaded_names', []))

        if not self.current_job_folder:
            return downloaded_ids, downloaded_names

        # Load from job-specific checkpoint if exists
        job_checkpoint_file = self.current_job_folder / 'checkpoint.json'
        if job_checkpoint_file.exists():
            try:
                with open(job_checkpoint_file, 'r', encoding='utf-8') as f:
                    job_data = json.load(f)
                    downloaded_ids.update(job_data.get('downloaded_ids', []))
                    downloaded_names.update(job_data.get('downloaded_names', []))
            except:
                pass

        # Scan existing PDF files to get names (only for existing jobs with new candidates)
        if scan_pdfs:
            print("   Scan des CVs existants...")
            for pdf_file in self.current_job_folder.glob('*.pdf'):
                # Format: "Jean Dupont_20251126_154317.pdf"
                name_part = pdf_file.stem.rsplit('_', 2)[0]  # Get "Jean Dupont"
                if name_part:
                    downloaded_names.add(name_part.lower())
            print(f"   {len(downloaded_names)} noms trouves dans les fichiers existants")

        return downloaded_ids, downloaded_names

    def _save_job_checkpoint(self, legacy_id: str, name: str = None):
        """Save checkpoint for current job folder"""
        if not self.current_job_folder:
            return

        job_checkpoint_file = self.current_job_folder / 'checkpoint.json'

        # Load existing
        job_data = {'downloaded_ids': [], 'downloaded_names': []}
        if job_checkpoint_file.exists():
            try:
                with open(job_checkpoint_file, 'r', encoding='utf-8') as f:
                    job_data = json.load(f)
                    if 'downloaded_names' not in job_data:
                        job_data['downloaded_names'] = []
            except:
                pass

        # Add new id
        if legacy_id and legacy_id not in job_data['downloaded_ids']:
            job_data['downloaded_ids'].append(legacy_id)

        # Add new name
        if name:
            clean_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip().lower()
            if clean_name and clean_name not in job_data['downloaded_names']:
                job_data['downloaded_names'].append(clean_name)

        # Save
        with open(job_checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(job_data, f, ensure_ascii=False, indent=2)

    def _fetch_candidates_batch(self, dispositions: list, sort_by: str = "APPLY_DATE", sort_order: str = "DESCENDING") -> tuple:
        """Fetch candidates with specific filters, returns (candidates_list, total_count)"""
        all_candidates = {}  # Use dict to dedupe by legacy_id
        offset = 0
        total_announced = 0

        while True:
            matches, total = self.fetch_candidates_api(
                offset=offset,
                limit=100,
                dispositions=dispositions,
                sort_by=sort_by,
                sort_order=sort_order
            )

            if offset == 0:
                total_announced = total

            if not matches:
                break

            for match in matches:
                try:
                    sub = match.get('candidateSubmission', {})
                    data = sub.get('data', {})
                    name = data.get('profile', {}).get('name', {}).get('displayName', 'Unknown')
                    legacy_id = data.get('legacyID')
                    resume = data.get('resume', {})
                    download_url = resume.get('downloadUrl') if resume else None

                    if legacy_id and legacy_id not in all_candidates:
                        all_candidates[legacy_id] = {
                            'name': name,
                            'legacy_id': legacy_id,
                            'download_url': download_url  # Can be None if no CV
                        }
                except:
                    continue

            if len(matches) < 100:
                break
            offset += 100
            time.sleep(0.3)

        return list(all_candidates.values()), total_announced

    def _download_all_candidates_api(self, job_total_candidates: int = 0):
        """Download all candidates via API with multiple passes to bypass 3000 limit

        Args:
            job_total_candidates: Total candidates from job listing (used to decide if we need multi-pass)
        """
        print("\nRecuperation des candidats via API...")

        # All disposition types
        all_dispositions = ["NEW", "PENDING", "PHONE_SCREENED", "INTERVIEWED", "OFFER_MADE", "REVIEWED"]
        all_candidates = {}  # key: legacy_id, value: candidate dict

        # Passe 1: Tri par date DESC (défaut)
        print("   Recuperation des candidats...")
        candidates, api_total = self._fetch_candidates_batch(all_dispositions, "APPLY_DATE", "DESCENDING")
        for c in candidates:
            if c['legacy_id'] not in all_candidates:
                all_candidates[c['legacy_id']] = c
        print(f"      {len(all_candidates)} recuperes")

        # Use job_total_candidates if available (more accurate), otherwise use API total
        total_expected = job_total_candidates if job_total_candidates > 0 else api_total

        # Si on a tout récupéré ou si <= 3000 attendus, pas besoin de passes supplémentaires
        if len(all_candidates) >= total_expected or total_expected <= 3000:
            pass  # On a tout, pas besoin de passes supplémentaires
        else:
            # Passes supplémentaires pour dépasser la limite de 3000
            print(f"   Limite API atteinte ({len(all_candidates)}/{total_expected}), passes supplementaires...")

            # Passe 2: Tri par date ASC
            print("   Passe 2: Par date (ancien -> recent)...")
            candidates, _ = self._fetch_candidates_batch(all_dispositions, "APPLY_DATE", "ASCENDING")
            new_count = 0
            for c in candidates:
                if c['legacy_id'] not in all_candidates:
                    all_candidates[c['legacy_id']] = c
                    new_count += 1
            print(f"      +{new_count} nouveaux, total: {len(all_candidates)}")

            # Passe 3: Tri par nom ASC (si encore manquant)
            if len(all_candidates) < total_expected:
                print("   Passe 3: Par nom (A -> Z)...")
                candidates, _ = self._fetch_candidates_batch(all_dispositions, "NAME", "ASCENDING")
                new_count = 0
                for c in candidates:
                    if c['legacy_id'] not in all_candidates:
                        all_candidates[c['legacy_id']] = c
                        new_count += 1
                print(f"      +{new_count} nouveaux, total: {len(all_candidates)}")

            # Passe 4: Tri par nom DESC (si encore manquant)
            if len(all_candidates) < total_expected:
                print("   Passe 4: Par nom (Z -> A)...")
                candidates, _ = self._fetch_candidates_batch(all_dispositions, "NAME", "DESCENDING")
                new_count = 0
                for c in candidates:
                    if c['legacy_id'] not in all_candidates:
                        all_candidates[c['legacy_id']] = c
                        new_count += 1
                print(f"      +{new_count} nouveaux, total: {len(all_candidates)}")

            # Passe 5: Par statut individuel (si >1000 manquants)
            if len(all_candidates) < total_expected and (total_expected - len(all_candidates)) > 1000:
                print("   Passe 5: Par statut individuel...")
                for disp in all_dispositions:
                    for sort_by in ["APPLY_DATE", "NAME"]:
                        for sort_order in ["ASCENDING", "DESCENDING"]:
                            candidates, _ = self._fetch_candidates_batch([disp], sort_by, sort_order)
                            new_count = 0
                            for c in candidates:
                                if c['legacy_id'] not in all_candidates:
                                    all_candidates[c['legacy_id']] = c
                                    new_count += 1
                            if new_count > 0:
                                print(f"      {disp} ({sort_by} {sort_order}): +{new_count}")
                print(f"      Total: {len(all_candidates)}")

        all_candidates_list = list(all_candidates.values())

        print(f"\n   Total attendu: {total_expected} | Recuperes: {len(all_candidates_list)}")

        if len(all_candidates_list) == 0 and total_expected > 0:
            print(f"   Aucun candidat recupere - job trop ancien ou donnees archivees")
            self.stats['archived'] += 1
            return

        if len(all_candidates_list) < total_expected:
            missing = total_expected - len(all_candidates_list)
            pct = (len(all_candidates_list) / total_expected) * 100
            print(f"   Note: {missing} candidats non recuperes ({pct:.1f}% recuperes)")

        # Load already processed names (PDFs + no_cv.txt)
        processed_names = set()
        if self.current_job_folder and self.current_job_folder.exists():
            # Scan PDF files
            for pdf_file in self.current_job_folder.glob('*.pdf'):
                # Format: "Jean Dupont_20251126_154317.pdf"
                name_part = pdf_file.stem.rsplit('_', 2)[0]  # Get "Jean Dupont"
                if name_part:
                    clean_name = "".join(ch for ch in name_part if ch.isalnum() or ch in (' ', '-', '_')).strip().lower()
                    processed_names.add(clean_name)

            # Load no_cv.txt (candidates without CV)
            no_cv_file = self.current_job_folder / 'no_cv.txt'
            if no_cv_file.exists():
                with open(no_cv_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        name = line.strip()
                        if name:
                            clean_name = "".join(ch for ch in name if ch.isalnum() or ch in (' ', '-', '_')).strip().lower()
                            processed_names.add(clean_name)

            if processed_names:
                print(f"   {len(processed_names)} candidats deja traites dans le dossier")

        # Separate candidates with CV and without CV
        candidates_with_cv = []
        candidates_no_cv = []
        for c in all_candidates_list:
            clean_name = "".join(ch for ch in c['name'] if ch.isalnum() or ch in (' ', '-', '_')).strip().lower()
            if clean_name in processed_names:
                continue  # Already processed
            if c['download_url']:
                candidates_with_cv.append(c)
            else:
                candidates_no_cv.append(c)

        # Save candidates without CV to no_cv.txt
        if candidates_no_cv and self.current_job_folder:
            no_cv_file = self.current_job_folder / 'no_cv.txt'
            with open(no_cv_file, 'a', encoding='utf-8') as f:
                for c in candidates_no_cv:
                    f.write(c['name'] + '\n')
            print(f"   {len(candidates_no_cv)} candidats sans CV (sauvegardes dans no_cv.txt)")

        already_done = len(all_candidates_list) - len(candidates_with_cv) - len(candidates_no_cv)
        print(f"\n   A telecharger: {len(candidates_with_cv)} (deja fait: {already_done}, sans CV: {len(candidates_no_cv)})")

        if not candidates_with_cv:
            print("   Tous les CVs sont deja telecharges!")
            return

        print(f"\n   Telechargement...\n")

        with tqdm(total=len(candidates_with_cv), desc="   CVs") as pbar:
            for candidate in candidates_with_cv:
                self.download_cv_api(candidate)
                pbar.update(1)

    # ==================== FRONTEND MODE (Selenium) ====================

    def run_frontend_single_job(self):
        """Run frontend mode for single job"""
        print("\n" + "=" * 60)
        print("👆 Naviguez vers le job et cliquez sur le premier candidat")
        print("   puis appuyez sur Entrée")
        print("=" * 60)
        input()

        # Get job name and create folder
        try:
            job_name = self.driver.execute_script("""
                const el = document.querySelector('[data-testid="job-title"]') ||
                           document.querySelector('h1');
                return el ? el.textContent.trim() : 'Job';
            """)
            self._create_job_folder(job_name)
            print(f"📁 Dossier: {self.current_job_folder}")
        except:
            pass

        self._download_all_candidates_frontend()

    def _download_all_candidates_frontend(self):
        """Download candidates using Selenium clicks"""
        print("\n🚀 Téléchargement via Selenium...\n")

        pbar = tqdm(desc="CVs")
        count = 0

        while count < self.max_cvs:
            # Get candidate name
            name = self._get_current_candidate_name()
            if not name:
                break

            # Check if already downloaded
            if name in self.checkpoint_data['downloaded_names']:
                self.stats['skipped'] += 1
            else:
                # Download CV
                if self._download_cv_frontend(name):
                    self.stats['downloaded'] += 1
                else:
                    self.stats['failed'] += 1

            self.stats['total_processed'] += 1
            count += 1
            pbar.update(1)

            # Go to next candidate
            if not self._go_to_next_candidate():
                break

            time.sleep(self.next_candidate_delay)

        pbar.close()

    def _get_current_candidate_name(self) -> Optional[str]:
        """Get name from page"""
        try:
            name = self.driver.execute_script("""
                const el = document.querySelector('[data-testid="name-plate-name-item"] span');
                return el ? el.textContent.trim() : null;
            """)
            return name
        except:
            return None

    def _download_cv_frontend(self, name: str) -> bool:
        """Download CV using click"""
        try:
            # Find download button
            for attempt in range(3):
                try:
                    download_link = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//a[text()='Download resume' or text()='Télécharger le CV']"
                        ))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_link)
                    time.sleep(0.2)
                    self.driver.execute_script("arguments[0].click();", download_link)
                    break
                except StaleElementReferenceException:
                    if attempt == 2:
                        return False
                    time.sleep(0.5)
                except TimeoutException:
                    return False

            time.sleep(self.download_delay)

            # Verify and rename file
            if self._verify_and_rename_download(name):
                self._save_checkpoint(name=name)
                return True
            return False

        except Exception as e:
            return False

    def _verify_and_rename_download(self, name: str) -> bool:
        """Verify download and rename file"""
        folder = self.current_job_folder or Path(self.download_folder)

        for _ in range(10):
            files = list(folder.glob("*.pdf"))
            for f in files:
                if f.stat().st_size > 1000 and name.split()[0].lower() not in f.name.lower():
                    # Rename file
                    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    new_name = folder / f"{safe_name}_{timestamp}.pdf"
                    f.rename(new_name)
                    return True
            time.sleep(0.5)

        return False

    def _go_to_next_candidate(self) -> bool:
        """Navigate to next candidate"""
        try:
            current_index = self.driver.execute_script("""
                const items = document.querySelectorAll('#hanselCandidateListContainer > div > ul > li[data-testid="CandidateListItem"]');
                for (let i = 0; i < items.length; i++) {
                    if (items[i].getAttribute('aria-current') === 'true' || items[i].getAttribute('data-selected') === 'true') {
                        return i;
                    }
                }
                return -1;
            """)

            if current_index == -1:
                return False

            # Click next candidate
            clicked = self.driver.execute_script(f"""
                const items = document.querySelectorAll('#hanselCandidateListContainer > div > ul > li[data-testid="CandidateListItem"]');
                const nextItem = items[{current_index + 1}];
                if (!nextItem) {{
                    // Try to load more
                    const btn = document.getElementById('fetchNextCandidates') ||
                               document.querySelector('[data-testid="fetchNextCandidates"]');
                    if (btn) {{ btn.click(); return 'loading'; }}
                    return null;
                }}
                const btn = nextItem.querySelector('button[data-testid="CandidateListItem-button"]');
                if (btn) {{
                    nextItem.scrollIntoView({{block: 'center'}});
                    btn.click();
                    return true;
                }}
                return null;
            """)

            if clicked == 'loading':
                time.sleep(2)
                return self._go_to_next_candidate()

            return clicked == True

        except Exception as e:
            return False

    # ==================== ALL JOBS MODE ====================

    def _format_date_fr(self, date_str: str) -> str:
        """Convertit 'septembre 22, 2025' en '22-09-2025'"""
        months_fr = {
            'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
            'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
            'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'
        }
        try:
            parts = date_str.lower().split()
            if len(parts) >= 3:
                month = months_fr.get(parts[0], '00')
                day = parts[1].replace(',', '').zfill(2)
                year = parts[2]
                return f"{day}-{month}-{year}"
        except:
            pass
        return date_str

    def _extract_jobs_from_page(self) -> list:
        """Extrait les jobs de la page actuelle du tableau HTML"""
        jobs = []
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[data-testid='job-row']")

            for row in rows:
                try:
                    # Titre du job - essayer plusieurs sélecteurs
                    title_elem = None
                    job_link = None

                    try:
                        title_elem = row.find_element(By.CSS_SELECTOR, "span[data-testid='UnifiedJobTldTitle'] a")
                    except:
                        pass

                    if not title_elem:
                        try:
                            title_elem = row.find_element(By.CSS_SELECTOR, "a[data-testid='UnifiedJobTldLink']")
                        except:
                            pass

                    if not title_elem:
                        continue

                    title = title_elem.text.strip()
                    job_link = title_elem.get_attribute('href')

                    if not title:
                        continue

                    # Nettoyer le titre
                    clean_title = self._clean_job_title(title)

                    # Date de publication
                    date_str = ""
                    date_formatted = ""
                    try:
                        date_elem = row.find_element(By.CSS_SELECTOR, "div[data-testid='job-created-date'] span[title]")
                        date_title = date_elem.get_attribute('title')
                        date_match = re.search(r'(\w+ \d+, \d+)', date_title)
                        date_str = date_match.group(1) if date_match else ""
                        date_formatted = self._format_date_fr(date_str)
                    except:
                        pass

                    # Nombre de candidats
                    total_candidates = 0
                    try:
                        candidates_elem = row.find_element(By.CSS_SELECTOR, "span[data-testid='candidates-pipeline-hosted-all-count']")
                        total_candidates = int(candidates_elem.text)
                    except:
                        pass

                    # Statut - essayer plusieurs sélecteurs
                    status = "ACTIVE"  # Par défaut si on ne trouve pas
                    try:
                        # Essayer le sélecteur principal
                        status_elem = row.find_element(By.CSS_SELECTOR, "div[data-testid='top-level-job-status']")
                        status_text = status_elem.text.strip().lower()

                        if 'ouvert' in status_text or 'open' in status_text:
                            status = 'ACTIVE'
                        elif 'suspendu' in status_text or 'pause' in status_text or 'paused' in status_text:
                            status = 'PAUSED'
                        elif 'fermé' in status_text or 'clos' in status_text or 'closed' in status_text:
                            status = 'CLOSED'
                    except:
                        pass

                    # Extraire l'employerJobId du lien
                    employer_job_id = None
                    if job_link:
                        # Try employerJobId first
                        if 'employerJobId=' in job_link:
                            match = re.search(r'employerJobId=([^&]+)', job_link)
                            if match:
                                employer_job_id = unquote(match.group(1))
                        # Try id parameter
                        elif 'id=' in job_link:
                            match = re.search(r'[?&]id=([^&]+)', job_link)
                            if match:
                                employer_job_id = unquote(match.group(1))

                    # If still no ID, create one from title + date
                    if not employer_job_id:
                        employer_job_id = f"{clean_title}_{date_formatted}".replace(' ', '_')

                    jobs.append({
                        'id': employer_job_id,
                        'title': title,
                        'title_clean': clean_title,
                        'status': status,
                        'date': date_formatted,
                        'total_candidates': total_candidates,
                        'job_link': job_link
                    })

                except:
                    continue

        except Exception as e:
            print(f"❌ Erreur extraction jobs: {e}")

        return jobs

    def _has_next_page(self) -> bool:
        """Vérifie si le bouton Suivant est actif"""
        try:
            next_btn = self.driver.find_element(By.ID, "ejsJobListPaginationNextBtn")
            return not next_btn.get_attribute('disabled')
        except:
            return False

    def _click_next_page(self) -> bool:
        """Clique sur le bouton Suivant"""
        try:
            next_btn = self.driver.find_element(By.ID, "ejsJobListPaginationNextBtn")
            if next_btn.get_attribute('disabled'):
                return False

            # Scroll vers le bouton et cliquer
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(0.5)
            next_btn.click()
            time.sleep(3)

            # Attendre que le tableau soit rechargé
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tr[data-testid='job-row']"))
            )
            return True
        except Exception as e:
            print(f"      Erreur pagination: {e}")
        return False

    def fetch_all_jobs(self) -> list:
        """Fetch all jobs from HTML table with pagination"""
        print("\nRecuperation de la liste des jobs...")

        # Construire l'URL avec les filtres de statut
        status_params = []
        if 'ACTIVE' in self.job_statuses:
            status_params.append('open')
        if 'PAUSED' in self.job_statuses:
            status_params.append('paused')
        if 'CLOSED' in self.job_statuses:
            status_params.append('closed')

        status_str = ','.join(status_params)
        jobs_url = f"https://employers.indeed.com/jobs?status={status_str}"

        print(f"   URL: {jobs_url}")
        self.driver.get(jobs_url)
        time.sleep(4)

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tr[data-testid='job-row']"))
            )
        except:
            print("Tableau des jobs non trouve")
            return []

        # Close any modals that might appear
        self._close_modals()

        # Récupérer le nombre total affiché
        try:
            total_text = self.driver.find_element(By.CSS_SELECTOR, "span[data-testid='job-count'], .css-1f9ew9y").text
            print(f"   Total affiche sur la page: {total_text}")
        except:
            pass

        all_jobs = []
        page = 1

        while True:
            print(f"   Page {page}...")

            # Attendre que les lignes soient chargées
            time.sleep(1)

            jobs = self._extract_jobs_from_page()

            # Ne pas filtrer par statut ici car l'URL filtre déjà
            all_jobs.extend(jobs)

            print(f"      {len(jobs)} jobs sur cette page (total: {len(all_jobs)})")

            if self._has_next_page():
                if not self._click_next_page():
                    break
                page += 1
                time.sleep(1)  # Attendre le chargement
            else:
                break

        print(f"\n{len(all_jobs)} jobs recuperes")

        # Afficher la liste des jobs trouvés
        print("\nListe des jobs:")
        print("-" * 60)
        for i, job in enumerate(all_jobs, 1):
            status_icon = "[O]" if job['status'] == 'ACTIVE' else "[P]" if job['status'] == 'PAUSED' else "[F]"
            print(f"   {i:3}. {status_icon} {job['title_clean']}")
            if job['date']:
                print(f"        Date: {job['date']} | Candidats: {job['total_candidates']}")
        print("-" * 60)

        return all_jobs

    def _find_existing_job_folders(self, jobs: list) -> dict:
        """Find which jobs already have folders in downloads

        Returns dict mapping job_id -> folder info, ensuring each folder is matched to only one job.
        Matching priority:
        1. Exact name + exact date (score 4) - must match
        2. Exact name only (score 2) - only if folder has no date or job has no date
        3. Partial name + exact date (score 3)
        4. Partial name only (score 1) - only if folder has no date or job has no date

        IMPORTANT: If both job and folder have dates, they MUST match for name matching.
        """
        existing = {}
        download_path = Path(self.download_folder)

        if not download_path.exists():
            return existing

        # Normalize function for comparison (removes accents for comparison only)
        def normalize(s):
            import unicodedata
            s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
            s = re.sub(r'[^a-z0-9\s]', '', s.lower())
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        # Get all folders with their info
        folder_info = {}
        for folder in download_path.iterdir():
            if folder.is_dir():
                # Format: "Nom du job (DD-MM-YYYY)"
                match = re.match(r'(.+) \((\d{2}-\d{2}-\d{4})\)$', folder.name)
                if match:
                    job_name = match.group(1)
                    date = match.group(2)
                    clean_name = self._clean_job_title(job_name)
                    normalized = normalize(clean_name)
                    # Count PDFs + no_cv.txt entries
                    cv_count = len(list(folder.glob('*.pdf')))
                    no_cv_file = folder / 'no_cv.txt'
                    if no_cv_file.exists():
                        with open(no_cv_file, 'r', encoding='utf-8') as f:
                            cv_count += sum(1 for line in f if line.strip())
                    folder_info[folder.name] = {
                        'original_name': job_name,
                        'clean_name': clean_name,
                        'normalized_name': normalized,
                        'date': date,
                        'cv_count': cv_count,
                        'matched_job_id': None  # Track which job matched this folder
                    }
                else:
                    clean_name = self._clean_job_title(folder.name)
                    normalized = normalize(clean_name)
                    # Count PDFs + no_cv.txt entries
                    cv_count = len(list(folder.glob('*.pdf')))
                    no_cv_file = folder / 'no_cv.txt'
                    if no_cv_file.exists():
                        with open(no_cv_file, 'r', encoding='utf-8') as f:
                            cv_count += sum(1 for line in f if line.strip())
                    folder_info[folder.name] = {
                        'original_name': folder.name,
                        'clean_name': clean_name,
                        'normalized_name': normalized,
                        'date': None,
                        'cv_count': cv_count,
                        'matched_job_id': None
                    }

        print(f"\n   {len(folder_info)} dossiers trouves dans '{self.download_folder}/'")

        # Match jobs with folders - each folder can only match ONE job
        # First pass: match jobs that have exact name + date match (highest priority)
        matched_count = 0
        for job in jobs:
            job_clean = job.get('title_clean', self._clean_job_title(job['title']))
            job_normalized = normalize(job_clean)
            job_date = job.get('date', '')
            job_id = job['id']

            # Only look for exact name + date matches in first pass
            if not job_date:
                continue

            for folder_name, info in folder_info.items():
                if info['matched_job_id'] is not None:
                    continue

                folder_normalized = info['normalized_name']
                folder_date = info['date']

                # Exact name + exact date match
                if job_normalized == folder_normalized and folder_date == job_date:
                    folder_info[folder_name]['matched_job_id'] = job_id
                    existing[job_id] = {
                        'title': job['title'],
                        'title_clean': job_clean,
                        'folder': folder_name,
                        'cv_count': info['cv_count'],
                        'total_candidates': job.get('total_candidates', 0),
                        'date': job_date
                    }
                    matched_count += 1
                    break

        print(f"   {matched_count} dossiers correspondent a des jobs")

        # Second pass: for jobs without date match, try name-only match (only for folders without date)
        for job in jobs:
            job_id = job['id']
            if job_id in existing:
                continue  # Already matched

            job_clean = job.get('title_clean', self._clean_job_title(job['title']))
            job_normalized = normalize(job_clean)
            job_date = job.get('date', '')

            best_match = None
            best_match_score = 0

            for folder_name, info in folder_info.items():
                if info['matched_job_id'] is not None:
                    continue

                folder_normalized = info['normalized_name']
                folder_date = info['date']

                # If both have dates and they don't match, skip this folder
                if job_date and folder_date and job_date != folder_date:
                    continue

                score = 0

                # Exact name match
                if job_normalized == folder_normalized:
                    # Higher score if dates match or no dates to compare
                    if job_date and folder_date and job_date == folder_date:
                        score = 4  # Best: exact name + exact date
                    elif not job_date or not folder_date:
                        score = 2  # Good: exact name, one or both missing date
                    # If dates don't match, score stays 0 (skip)

                # Partial match (one contains the other) - only for longer names
                elif len(job_normalized) >= 10 and len(folder_normalized) >= 10:
                    if job_normalized in folder_normalized or folder_normalized in job_normalized:
                        if job_date and folder_date and job_date == folder_date:
                            score = 3  # Good: partial name + exact date
                        elif not job_date or not folder_date:
                            score = 1  # OK: partial name, one or both missing date
                        # If dates don't match, score stays 0 (skip)

                if score > best_match_score:
                    best_match_score = score
                    best_match = folder_name

            # If we found a match, mark the folder as matched
            if best_match and best_match_score > 0:
                folder_info[best_match]['matched_job_id'] = job_id
                existing[job_id] = {
                    'title': job['title'],
                    'title_clean': job_clean,
                    'folder': best_match,
                    'cv_count': folder_info[best_match]['cv_count'],
                    'total_candidates': job.get('total_candidates', 0),
                    'date': job_date
                }

        return existing

    def _ask_skip_existing_jobs(self, jobs: list, existing_jobs: dict) -> list:
        """Ask user which existing jobs to skip

        Args:
            jobs: List of all jobs
            existing_jobs: Dict of jobs that have existing folders
        """
        if not existing_jobs:
            return jobs

        print("\n" + "=" * 60)
        print("JOBS DEJA PRESENTS DANS LE DOSSIER DOWNLOADS:")
        print("=" * 60)

        jobs_with_new = []
        jobs_complete = []

        for job_id, info in existing_jobs.items():
            cv_count = info['cv_count']
            total = info['total_candidates']
            # Use cleaned title for display
            title = info.get('title_clean', info['title'])
            folder = info['folder']
            date = info.get('date', '')

            # Format title with date for clarity
            title_with_date = f"{title} ({date})" if date else title

            if total > cv_count:
                jobs_with_new.append((job_id, info))
                print(f"   [NEW] {title_with_date}")
                print(f"         Dossier: {folder}")
                print(f"         {cv_count} CVs telecharges / {total} candidats (+{total - cv_count} nouveaux)")
            else:
                jobs_complete.append((job_id, info))
                print(f"   [OK]  {title_with_date} ({cv_count} CVs)")

        print()
        if jobs_with_new:
            print(f"   {len(jobs_with_new)} jobs avec nouveaux candidats")
        print(f"   {len(jobs_complete)} jobs complets")
        print()
        print("Options:")
        print("   [S] SkipAll - Ignorer TOUS les jobs existants")
        print("   [N] NewOnly - Telecharger seulement les jobs avec nouveaux candidats")
        print("   [K] KeepAll - Telecharger quand meme tous les jobs")
        print()

        while True:
            choice = input("Votre choix (S/N/K): ").strip().upper()

            if choice == 'S':
                # Skip all existing
                jobs_to_skip = set(existing_jobs.keys())
                filtered_jobs = [j for j in jobs if j['id'] not in jobs_to_skip]
                print(f"\n{len(jobs_to_skip)} jobs ignores")
                return filtered_jobs

            elif choice == 'N':
                # Only jobs with new candidates
                jobs_with_new_ids = set(job_id for job_id, _ in jobs_with_new)
                filtered_jobs = [j for j in jobs if j['id'] in jobs_with_new_ids]
                print(f"\n{len(jobs_complete)} jobs complets ignores, {len(filtered_jobs)} a traiter")
                return filtered_jobs

            elif choice == 'K':
                # Keep all
                print("\nTous les jobs seront traites")
                return jobs

            print("Choix invalide, tapez S, N ou K")

    def _filter_old_jobs(self, jobs: list) -> list:
        """Filter out jobs older than 2 years (Indeed archives candidate data after ~2 years)"""
        from datetime import datetime, timedelta

        two_years_ago = datetime.now() - timedelta(days=730)  # ~2 years
        filtered_jobs = []
        old_jobs_count = 0

        for job in jobs:
            job_date = job.get('date', '')
            if job_date:
                try:
                    # Parse date format: DD-MM-YYYY
                    parsed_date = datetime.strptime(job_date, '%d-%m-%Y')
                    if parsed_date < two_years_ago:
                        old_jobs_count += 1
                        continue
                except:
                    pass
            filtered_jobs.append(job)

        if old_jobs_count > 0:
            print(f"\n   {old_jobs_count} jobs de plus de 2 ans ignores (donnees archivees par Indeed)")

        return filtered_jobs

    def run_all_jobs(self):
        """Process all jobs"""
        jobs = self.fetch_all_jobs()

        if not jobs:
            print("Aucun job trouve")
            return

        # Filter out jobs older than 2 years (Indeed archives data)
        jobs = self._filter_old_jobs(jobs)

        if not jobs:
            print("Aucun job recent a traiter (tous > 2 ans)")
            return

        # Check for existing folders (compare by name, not checkpoint)
        existing_jobs = self._find_existing_job_folders(jobs)

        if existing_jobs:
            jobs = self._ask_skip_existing_jobs(jobs, existing_jobs)

        if not jobs:
            print("Aucun job a traiter!")
            return

        print(f"\n{len(jobs)} jobs a traiter")
        print("=" * 60)

        for i, job in enumerate(jobs):
            title_display = job.get('title_clean', job['title'])
            print(f"\n[{i+1}/{len(jobs)}] {title_display}")
            print(f"         Status: {job['status']}, Date: {job['date'] or 'N/A'}, Candidats: {job.get('total_candidates', '?')}")

            self.current_job_id = job['id']
            self.current_job_name = job['title']
            self._create_job_folder(job['title'], job['date'])

            if self.mode == 'backend':
                # Close any modals that might appear
                self._close_modals()
                self._download_all_candidates_api(job.get('total_candidates', 0))
            else:
                # Navigate to job
                self.driver.get(f"https://employers.indeed.com/candidates?selectedJobs={job['id']}")
                time.sleep(3)
                # Close any modals that might appear
                self._close_modals()
                self._download_all_candidates_frontend()

            self._save_checkpoint(job_id=job['id'])
            print(f"   Job termine: {title_display}")

    # ==================== MAIN ====================

    def print_statistics(self):
        """Print final statistics"""
        print("\n" + "=" * 60)
        print("STATISTIQUES")
        print("=" * 60)
        print(f"Total traites:  {self.stats['total_processed']}")
        print(f"Telecharges:    {self.stats['downloaded']}")
        print(f"Ignores:        {self.stats['skipped']}")
        print(f"Echecs:         {self.stats['failed']}")
        if self.stats['archived'] > 0:
            print(f"Jobs archives:  {self.stats['archived']} (donnees non disponibles)")

        if self.start_time:
            elapsed = time.time() - self.start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            print(f"\n⏱️ Temps total: {hours}h {minutes}m {seconds}s")

            if self.stats['downloaded'] > 0:
                avg = elapsed / self.stats['downloaded']
                print(f"⏱️ Moyenne/CV:  {avg:.1f}s")

        print("=" * 60)

    def run(self):
        """Main execution"""
        try:
            self.show_menu()

            if not self.setup_chrome():
                return

            self.start_time = time.time()

            if self.job_mode == 'single':
                if self.mode == 'backend':
                    self.run_backend_single_job()
                else:
                    self.run_frontend_single_job()
            else:
                self.run_all_jobs()

            self.print_statistics()

        except KeyboardInterrupt:
            print("\n\n⚠️ Interrompu par l'utilisateur")
            self.print_statistics()

        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            import traceback
            traceback.print_exc()

        finally:
            if self.driver:
                input("\nAppuyez sur Entrée pour fermer Chrome...")
                self.driver.quit()


def main():
    downloader = IndeedDownloader()
    downloader.run()


if __name__ == "__main__":
    main()
