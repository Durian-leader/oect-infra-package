import json

data = [
    r"C:\Users\lidonghaowsl\develop\hdd\Source\20250815BBL不同封装稳定性"
]

with open("ps_paths.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
