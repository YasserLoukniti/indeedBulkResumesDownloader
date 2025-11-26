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
    txt_file = r"C:\Users\yass_\Downloads\employers.indeed.com_cookies.txt"
    json_file = r"C:\Users\yass_\Desktop\indeed-cv-downloader\logs\indeed_cookies.json"

    convert_netscape_to_json(txt_file, json_file)
    print("\n✅ Conversion terminée!")
    print("Vous pouvez maintenant lancer: python indeed_with_cookies.py")
