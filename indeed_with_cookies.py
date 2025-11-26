"""
Indeed CV Downloader - Using existing browser session cookies
No login required - bypasses robot detection by reusing your authenticated session
"""

import os
import json
import time
import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
import chromedriver_autoinstaller
from tqdm import tqdm

# Load environment variables
load_dotenv('.env.config')


class IndeedCVDownloaderWithCookies:
    """
    Downloads CVs using your existing browser session
    IMPORTANT: Run this while your Chrome browser is closed
    """

    def __init__(self, config_path: str = "config.json"):
        """Initialize the downloader"""
        # Load delays from environment
        self.download_delay = float(os.getenv('DOWNLOAD_DELAY', '0.5'))
        self.next_candidate_delay = float(os.getenv('NEXT_CANDIDATE_DELAY', '1.0'))
        self.between_candidates_delay = float(os.getenv('BETWEEN_CANDIDATES_DELAY', '0.5'))
        self.page_load_delay = float(os.getenv('PAGE_LOAD_DELAY', '5'))
        self.max_cvs = int(os.getenv('MAX_CVS', '10'))
        self.download_verify_timeout = int(os.getenv('DOWNLOAD_VERIFY_TIMEOUT', '30'))

        # Setup directories
        self.download_folder = Path(os.getenv('DOWNLOAD_FOLDER', 'downloads'))
        self.log_folder = Path(os.getenv('LOG_FOLDER', 'logs'))
        self.download_folder.mkdir(exist_ok=True)
        self.log_folder.mkdir(exist_ok=True)

        # Cookie file
        self.cookie_file = Path(os.getenv('COOKIE_FILE', 'logs/indeed_cookies.json'))

        # Load old config for compatibility
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        except:
            self.config = {}

        # Checkpoint
        self.checkpoint_file = self.log_folder / "checkpoint.json"
        self.checkpoint_data = self._load_checkpoint()

        # Statistics
        self.stats = {
            'total_processed': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'skipped': 0
        }

        self.driver = None
        self.wait = None

        # Stuck detection
        self.last_position = None
        self.stuck_count = 0
        self.max_stuck_attempts = 3

        print("""
╔════════════════════════════════════════════════════════════╗
║   Indeed CV Downloader - Cookie Session Method            ║
║   Contourne la détection robot en réutilisant              ║
║   votre session de navigateur actuelle                     ║
╚════════════════════════════════════════════════════════════╝
        """)

    def _load_checkpoint(self) -> dict:
        """Load checkpoint"""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'downloaded_names': [], 'last_position': 0}

    def _save_checkpoint(self, candidate_name: str, position: int):
        """Save checkpoint"""
        if candidate_name not in self.checkpoint_data['downloaded_names']:
            self.checkpoint_data['downloaded_names'].append(candidate_name)
        self.checkpoint_data['last_position'] = position

        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.checkpoint_data, f, ensure_ascii=False, indent=2)

    def export_cookies_from_chrome(self):
        """
        Instructions to export cookies from Chrome
        User must do this manually first
        """
        print("""
📋 ÉTAPE 1: EXPORTER VOS COOKIES CHROME

Vous devez d'abord exporter vos cookies Indeed depuis Chrome:

1. Ouvrez Chrome et allez sur: https://employers.indeed.com/candidates
2. Appuyez sur F12 pour ouvrir DevTools
3. Allez dans l'onglet "Application" (ou "Storage")
4. Dans le menu de gauche, cliquez sur "Cookies" → "https://employers.indeed.com"
5. Vous verrez la liste de tous les cookies

OPTION A - Extension Chrome (RECOMMANDÉ):
-----------------------------------------
1. Installez l'extension: "EditThisCookie" ou "Get cookies.txt"
2. Cliquez sur l'icône de l'extension
3. Cliquez sur "Export" → choisissez format "JSON" ou "Netscape"
4. Sauvegardez dans: {self.cookie_file}

OPTION B - Copie manuelle (plus complexe):
------------------------------------------
1. Copiez TOUS les cookies (Name, Value, Domain, Path, Expires)
2. Créez un fichier JSON avec ce format:
   [
     {{"name": "nom_cookie", "value": "valeur", "domain": ".indeed.com"}},
     ...
   ]

⚠️ IMPORTANT: Fermez Chrome complètement après avoir exporté les cookies!

Appuyez sur Entrée quand c'est fait...
        """)
        input()

    def load_cookies_manual(self):
        """Load cookies from JSON file"""
        print("\n🔍 Recherche du fichier de cookies...")

        # Check for cookie file
        if not self.cookie_file.exists():
            print(f"❌ Fichier de cookies introuvable: {self.cookie_file}")
            print("\nVoulez-vous:")
            print("1. Réessayer l'export des cookies")
            print("2. Utiliser un autre fichier")
            choice = input("Choix (1/2): ")

            if choice == "2":
                cookie_path = input("Chemin vers le fichier de cookies: ")
                self.cookie_file = Path(cookie_path)

        try:
            # Try JSON format first
            with open(self.cookie_file, 'r') as f:
                cookies = json.load(f)

            print(f"✅ Chargé {len(cookies)} cookies depuis {self.cookie_file}")
            return cookies

        except json.JSONDecodeError:
            # Try pickle format
            try:
                with open(self.cookie_file, 'rb') as f:
                    cookies = pickle.load(f)
                print(f"✅ Chargé {len(cookies)} cookies (format pickle)")
                return cookies
            except:
                print("❌ Format de cookies invalide")
                return None

    def setup_driver(self):
        """Setup Chrome driver (clean profile with cookies only)"""
        chrome_options = webdriver.ChromeOptions()

        print("✅ Création d'une session propre avec vos cookies")

        # Download settings
        download_dir = str(self.download_folder.absolute())
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # Anti-detection settings
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')

        # Initialize driver with chromedriver-autoinstaller
        chromedriver_autoinstaller.install()
        self.driver = webdriver.Chrome(options=chrome_options)

        # Additional anti-detection
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, self.config.get('page_load_timeout', 30))

        print("✅ Chrome driver initialized")

    def load_session_with_cookies(self, cookies):
        """Load Indeed with saved cookies"""
        print("\n🔐 Chargement de la session avec vos cookies...")

        # First navigate to Indeed Employers (must match cookie domain)
        self.driver.get("https://employers.indeed.com/candidates")
        time.sleep(3)

        # Add each cookie
        for cookie in cookies:
            try:
                # Clean cookie data
                cookie_data = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.indeed.com'),
                }

                # Optional fields
                if 'path' in cookie:
                    cookie_data['path'] = cookie['path']
                if 'expiry' in cookie:
                    cookie_data['expiry'] = cookie['expiry']
                if 'secure' in cookie:
                    cookie_data['secure'] = cookie['secure']
                if 'httpOnly' in cookie:
                    cookie_data['httpOnly'] = cookie['httpOnly']

                self.driver.add_cookie(cookie_data)

            except Exception as e:
                print(f"⚠️ Erreur lors de l'ajout du cookie {cookie.get('name')}: {e}")
                continue

        print(f"✅ {len(cookies)} cookies chargés")

        # Refresh to apply cookies
        self.driver.refresh()
        time.sleep(3)

        # Verify we're logged in
        current_url = self.driver.current_url
        if "employers.indeed.com" in current_url and "login" not in current_url:
            print("✅ Session restaurée avec succès!")
            return True
        else:
            print("❌ Échec de la restauration de session")
            print(f"URL actuelle: {current_url}")
            return False

    def get_current_candidate_name(self) -> Optional[str]:
        """Extract current candidate name"""
        try:
            name_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "main h3"))
            )
            return name_element.text.strip()
        except:
            return None

    def download_cv(self) -> bool:
        """Download CV for current candidate - optimized for speed"""
        try:
            # Get candidate name from the list (faster than waiting for full page load)
            print("   🔍 Récupération du nom depuis la liste...")
            candidate_name = self._get_selected_candidate_name_from_list()
            if not candidate_name:
                print("   🔍 Nom non trouvé dans liste, attente du chargement page...")
                candidate_name = self.get_current_candidate_name()

            if not candidate_name:
                print("❌ Impossible d'identifier le candidat")
                return False

            # Check if already downloaded
            if candidate_name in self.checkpoint_data['downloaded_names']:
                print(f"⏭️ Déjà téléchargé: {candidate_name}")
                self.stats['skipped'] += 1
                return True

            print(f"📥 Candidat: {candidate_name}")

            # Find download link - check PRESENCE (not clickable, we'll use JS click)
            # Button text: "Download resume" (English) or "Télécharger le CV" (French)
            print("   🔍 Recherche du bouton CV...")
            download_link = None

            # Quick check for both versions using XPath OR condition
            try:
                download_link = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//a[text()='Download resume' or text()='Télécharger le CV']"
                    ))
                )
                print(f"   ✅ Bouton trouvé: '{download_link.text}'")
            except TimeoutException:
                print(f"   ⚠️ Aucun bouton CV trouvé après 5s")
                self.stats['failed_downloads'] += 1
                return False

            # Scroll into view and click
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_link)
            time.sleep(0.2)
            print("   🖱️ Clic sur le bouton...")
            self.driver.execute_script("arguments[0].click();", download_link)
            print("   ✅ Clic effectué!")

            # Short delay for download to start
            print(f"   ⏳ Attente téléchargement ({self.download_delay}s)...")
            time.sleep(self.download_delay)

            # Verify and rename
            print("   🔍 Vérification du téléchargement...")
            if self._verify_download():
                self._rename_latest_file(candidate_name)

                position = self._get_current_position()
                self._save_checkpoint(candidate_name, position or 0)

                self.stats['successful_downloads'] += 1
                print(f"✅ Téléchargé: {candidate_name}")
                return True
            else:
                self.stats['failed_downloads'] += 1
                print(f"⚠️ Échec vérification téléchargement: {candidate_name}")
                return False

        except Exception as e:
            self.stats['failed_downloads'] += 1
            print(f"❌ Erreur téléchargement: {str(e)}")
            return False

    def _get_selected_candidate_name_from_list(self) -> Optional[str]:
        """Get name of selected candidate from the sidebar list (faster)"""
        try:
            selected = self.driver.find_element(
                By.CSS_SELECTOR,
                "li[data-testid='CandidateListItem'][data-selected='true'] button[data-testid='CandidateListItem-button']"
            )
            return selected.text.strip()
        except:
            return None

    def _verify_download(self, timeout: int = None) -> bool:
        """Verify download completed"""
        if timeout is None:
            timeout = self.download_verify_timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            files = list(self.download_folder.glob('*.pdf'))
            for file in files:
                if time.time() - file.stat().st_mtime < 5:
                    return True
            time.sleep(0.5)
        return False

    def _rename_latest_file(self, candidate_name: str):
        """Rename downloaded file"""
        try:
            files = list(self.download_folder.glob('*.pdf'))
            if not files:
                return

            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', candidate_name).strip()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_name = self.download_folder / f"{safe_name}_{timestamp}.pdf"

            latest_file.rename(new_name)
            print(f"📝 Renommé: {new_name.name}")

        except Exception as e:
            print(f"⚠️ Erreur renommage: {e}")

    def _get_current_position(self) -> Optional[int]:
        """Get current position from page"""
        try:
            status_text = self.driver.find_element(By.XPATH, "//*[contains(text(), 'sur')]").text
            match = re.search(r'(\d+)\s+sur', status_text)
            if match:
                return int(match.group(1))
        except:
            pass
        return None

    def get_candidate_list_items(self):
        """Get all candidate list items"""
        try:
            container = self.driver.find_element(By.CSS_SELECTOR, "#hanselCandidateListContainer > div > ul")
            items = container.find_elements(By.CSS_SELECTOR, "li[data-testid='CandidateListItem']")
            return items
        except Exception as e:
            print(f"⚠️ Erreur récupération liste: {e}")
            return []

    def get_current_candidate_index(self):
        """Get index of currently selected candidate in the list"""
        try:
            items = self.get_candidate_list_items()
            for i, item in enumerate(items):
                if item.get_attribute("data-selected") == "true":
                    return i
            return -1
        except:
            return -1

    def click_show_more(self) -> bool:
        """Click 'Afficher plus' button to load more candidates"""
        try:
            show_more_btn = self.driver.find_element(By.ID, "fetchNextCandidates")
            if show_more_btn:
                print("   📜 Clic sur 'Afficher plus'...")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_more_btn)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", show_more_btn)
                time.sleep(2)  # Wait for new candidates to load
                print("   ✅ Plus de candidats chargés!")
                return True
        except NoSuchElementException:
            print("   ℹ️ Bouton 'Afficher plus' non trouvé")
            return False
        except Exception as e:
            print(f"   ⚠️ Erreur 'Afficher plus': {e}")
            return False

    def _get_candidate_names_from_list(self, items, start_index: int) -> list:
        """Get names of candidates from list starting at index"""
        names = []
        for i in range(start_index, len(items)):
            try:
                button = items[i].find_element(By.CSS_SELECTOR, "button[data-testid='CandidateListItem-button']")
                names.append((i, button.text.strip()))
            except:
                continue
        return names

    def _find_next_not_downloaded(self, items, start_index: int) -> int:
        """Find next candidate that hasn't been downloaded yet (smart skip)"""
        candidates = self._get_candidate_names_from_list(items, start_index)
        skipped_count = 0

        for idx, name in candidates:
            if name not in self.checkpoint_data['downloaded_names']:
                if skipped_count > 0:
                    print(f"   ⏭️ Skip intelligent: {skipped_count} candidats déjà téléchargés")
                return idx
            skipped_count += 1
            self.stats['skipped'] += 1

        # All remaining are downloaded
        if skipped_count > 0:
            print(f"   ⏭️ Skip intelligent: {skipped_count} candidats déjà téléchargés (fin de liste)")
        return -1  # All downloaded

    def _check_if_stuck(self) -> bool:
        """Check if we're stuck on the same position"""
        current_pos = self._get_current_position()
        if current_pos is None:
            return False

        if self.last_position == current_pos:
            self.stuck_count += 1
            if self.stuck_count >= self.max_stuck_attempts:
                print(f"⚠️ Bloqué sur position {current_pos} après {self.stuck_count} tentatives")
                return True
        else:
            self.stuck_count = 0
            self.last_position = current_pos

        return False

    def go_to_next_candidate(self) -> bool:
        """Navigate to next candidate by clicking in the list"""
        try:
            # Check if stuck on same position
            if self._check_if_stuck():
                print("🔄 Tentative de déblocage via la liste...")
                return self._force_next_in_list()

            items = self.get_candidate_list_items()
            current_index = self.get_current_candidate_index()

            if current_index == -1:
                print("   ⚠️ Candidat actuel non trouvé dans la liste")
                return False

            print(f"   📋 Position actuelle: {current_index + 1}/{len(items)}")

            # Smart skip: find next candidate that hasn't been downloaded
            next_index = self._find_next_not_downloaded(items, current_index + 1)

            # If all remaining in current list are downloaded, try loading more
            while next_index == -1:
                print(f"   📋 Tous les candidats visibles sont téléchargés, chargement de plus...")
                if self.click_show_more():
                    time.sleep(1)
                    items = self.get_candidate_list_items()
                    # Search from where we were
                    next_index = self._find_next_not_downloaded(items, current_index + 1)
                    if next_index == -1:
                        # Still nothing new, continue loading
                        old_len = len(items)
                        if self.click_show_more():
                            time.sleep(1)
                            items = self.get_candidate_list_items()
                            if len(items) == old_len:
                                print("   ⚠️ Plus de candidats à charger")
                                return False
                            next_index = self._find_next_not_downloaded(items, current_index + 1)
                        else:
                            print("   ⚠️ Fin de la liste, tous téléchargés")
                            return False
                else:
                    print("   ⚠️ Impossible de charger plus de candidats")
                    return False

            # Click on next candidate
            next_item = items[next_index]
            button = next_item.find_element(By.CSS_SELECTOR, "button[data-testid='CandidateListItem-button']")
            candidate_name = button.text.strip()
            print(f"👆 Clic sur candidat #{next_index + 1}: {candidate_name}")

            # Scroll the element into view before clicking
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_item)
            time.sleep(0.3)

            # Use JavaScript click to avoid interception issues
            self.driver.execute_script("arguments[0].click();", button)
            time.sleep(self.next_candidate_delay)
            print("   ✅ Candidat chargé!")
            return True

        except Exception as e:
            print(f"❌ Erreur navigation: {e}")
            return False

    def _force_next_in_list(self) -> bool:
        """Force click on next candidate in list when stuck"""
        try:
            items = self.get_candidate_list_items()
            current_index = self.get_current_candidate_index()

            if current_index == -1 or current_index + 1 >= len(items):
                # Try to load more
                if self.click_show_more():
                    time.sleep(1)
                    items = self.get_candidate_list_items()
                    current_index = self.get_current_candidate_index()

            next_index = current_index + 1
            if next_index < len(items):
                next_item = items[next_index]
                button = next_item.find_element(By.CSS_SELECTOR, "button[data-testid='CandidateListItem-button']")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_item)
                time.sleep(0.3)
                self.driver.execute_script("arguments[0].click();", button)
                time.sleep(self.next_candidate_delay)
                # Reset stuck counter after successful force
                self.stuck_count = 0
                self.last_position = None
                print("✅ Déblocage réussi!")
                return True

            return False
        except Exception as e:
            print(f"❌ Échec déblocage: {e}")
            return False

    def run(self):
        """Main execution"""
        try:
            # Step 1: Load cookies
            cookies = self.load_cookies_manual()
            if not cookies:
                print("❌ Impossible de charger les cookies. Abandon.")
                return

            # Step 3: Setup driver
            self.setup_driver()

            # Step 4: Load session
            if not self.load_session_with_cookies(cookies):
                print("❌ Échec du chargement de la session. Vérifiez vos cookies.")
                return

            # Step 5: Wait for user to select first candidate
            print("\n" + "="*60)
            print("👆 CLIQUEZ SUR LE PREMIER CANDIDAT à télécharger")
            print("   puis appuyez sur Entrée pour démarrer")
            print("="*60)
            input()

            # Verify a candidate is selected
            if self.get_current_candidate_index() == -1:
                print("⚠️ Aucun candidat sélectionné! Veuillez en sélectionner un.")
                input("Appuyez sur Entrée quand c'est fait...")

            # Get total
            total = self._get_total_candidates()
            if total:
                print(f"📊 Total: {total} candidats")

            # Step 7: Process all
            print("\n🚀 Démarrage des téléchargements...\n")

            if total:
                pbar = tqdm(total=total, desc="CVs", initial=self.checkpoint_data.get('last_position', 0))
            else:
                pbar = tqdm(desc="CVs")

            count = 0
            max_count = self.max_cvs

            while count < max_count:
                self.download_cv()
                self.stats['total_processed'] += 1
                count += 1
                pbar.update(1)

                if not self.go_to_next_candidate():
                    break

                # Delay between candidates
                time.sleep(self.between_candidates_delay)

            pbar.close()
            self.print_statistics()

        except KeyboardInterrupt:
            print("\n\n⚠️ Interrompu par l'utilisateur")
            self.print_statistics()

        except Exception as e:
            print(f"\n❌ Erreur fatale: {e}")

        finally:
            if self.driver:
                self.driver.quit()

    def _get_total_candidates(self) -> Optional[int]:
        """Get total from page"""
        try:
            status = self.driver.find_element(By.XPATH, "//*[contains(text(), 'sur')]").text
            match = re.search(r'sur\s+(\d+)', status)
            if match:
                return int(match.group(1))
        except:
            pass
        return None

    def print_statistics(self):
        """Print stats"""
        print("\n" + "=" * 60)
        print("📊 STATISTIQUES")
        print("=" * 60)
        print(f"Total:      {self.stats['total_processed']}")
        print(f"✅ Réussis:  {self.stats['successful_downloads']}")
        print(f"❌ Échecs:   {self.stats['failed_downloads']}")
        print(f"⏭️ Ignorés:  {self.stats['skipped']}")

        if self.stats['total_processed'] > 0:
            rate = (self.stats['successful_downloads'] / self.stats['total_processed'] * 100)
            print(f"Taux:       {rate:.2f}%")

        print("=" * 60)


def main():
    downloader = IndeedCVDownloaderWithCookies()
    downloader.run()


if __name__ == "__main__":
    main()
