from heroes import load_hero_names
from stratz import get_draft

hero_names = load_hero_names()
players = get_draft([1], [14])

print(len(hero_names))
print(len(players))