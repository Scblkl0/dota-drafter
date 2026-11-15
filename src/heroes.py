import json
from pathlib import Path

import requests

HEROES_URL = "https://api.opendota.com/api/heroes"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = PROJECT_ROOT / "data" / "heroes.json"


def load_hero_names():
    if not CACHE_FILE.exists():
        response = requests.get(HEROES_URL, timeout=10)
        response.raise_for_status()
        heroes = response.json()

        CACHE_FILE.parent.mkdir(exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(heroes, f, ensure_ascii=False, indent=2)

    with open(CACHE_FILE, encoding="utf-8") as f:
        heroes = json.load(f)

    return {hero["id"]: hero["localized_name"] for hero in heroes}


if __name__ == "__main__":
    names = load_hero_names()
    print(len(names))
    print(names[1], names[14])