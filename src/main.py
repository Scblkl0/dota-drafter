from heroes import load_hero_names
from stratz import get_draft

LETTER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "F": 5}


def show_suggestions(players, slot, hero_names, picked, top=10):
    player = None
    for p in players:
        if p["slot"] == slot:
            player = p
            break

    if player is None or player["heroes"] is None:
        print(f"No suggestions for slot {slot}")
        return

    candidates = [h for h in player["heroes"] if h["heroId"] not in picked]
    candidates = sorted(candidates, key=lambda h: LETTER_ORDER.get(h["letter"], 99))

    print(f"Slot {slot} ({player['position']}):")
    for i, hero in enumerate(candidates[:top], start=1):
        name = hero_names.get(hero["heroId"], f"Hero {hero['heroId']}")
        print(f"{i}. {name} — {hero['letter']}")


if __name__ == "__main__":
    radiant = [1]
    dire = [14]

    hero_names = load_hero_names()
    players = get_draft(radiant, dire)

    for slot in range(len(radiant), 5):
        show_suggestions(players, slot, hero_names, radiant + dire)
        print()