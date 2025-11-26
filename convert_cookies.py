"""
Convert Netscape cookies.txt to JSON format
"""

import json

def convert_netscape_to_json(txt_file, json_file):
    """Convert Netscape cookie format to JSON"""
    cookies = []

    with open(txt_file, 'r', encoding='utf-8') as f:
        for line in f:
            # Skip comments and empty lines
            if line.startswith('#') or not line.strip():
                continue

            # Parse Netscape format
            parts = line.strip().split('\t')

            if len(parts) >= 7:
                domain = parts[0]
                flag = parts[1]
                path = parts[2]
                secure = parts[3] == 'TRUE'
                expiry = parts[4]
                name = parts[5]
                value = parts[6]

                cookie = {
                    'name': name,
                    'value': value,
                    'domain': domain,
                    'path': path,
                    'secure': secure,
                    'httpOnly': False
                }

                # Add expiry if valid
                try:
                    cookie['expiry'] = int(expiry)
                except:
                    pass

                cookies.append(cookie)

    # Save as JSON
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, indent=2)

    print(f"✅ Converti {len(cookies)} cookies")
    print(f"📁 Fichier créé: {json_file}")

if __name__ == "__main__":
    import os
    import sys

    # Get the directory where the exe/script is located
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # Fixed paths in logs folder
    logs_dir = os.path.join(base_dir, "logs")
    txt_file = os.path.join(logs_dir, "indeed_cookies.txt")
    json_file = os.path.join(logs_dir, "indeed_cookies.json")

    # Create logs directory if needed
    os.makedirs(logs_dir, exist_ok=True)

    print("=" * 50)
    print("  Convertisseur Cookies Netscape -> JSON")
    print("=" * 50)
    print(f"\nInput:  {txt_file}")
    print(f"Output: {json_file}")

    # Check if input exists
    if not os.path.exists(txt_file):
        print(f"\n❌ Fichier introuvable: {txt_file}")
        print("\n📋 Placez votre fichier cookies.txt dans le dossier 'logs'")
        print("   et renommez-le en 'indeed_cookies.txt'")
        input("\nAppuyez sur Entrée pour quitter...")
        sys.exit(1)

    convert_netscape_to_json(txt_file, json_file)
    print("\n✅ Conversion terminée!")
    print("Vous pouvez maintenant lancer IndeedCVDownloader.exe")
    input("\nAppuyez sur Entrée pour quitter...")
