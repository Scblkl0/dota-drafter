import requests
from collections import Counter
opendota_heroes = "https://api.opendota.com/api/heroes"
response = requests.get(opendota_heroes, timeout=10)
heroes = response.json()

print(len(heroes))
print(heroes[0])
print(heroes[0]["name"])

print("----------------")

heroes_names_by_id = {}
for hero in heroes:
    heroes_names_by_id[hero["id"]] = hero["localized_name"]

print(heroes_names_by_id[74])

print("----------------")

att_counter={}
for hero in heroes:
    primary_attribute = hero["primary_attr"]
    att_counter[primary_attribute] = att_counter.get(primary_attribute, 0) + 1

print(att_counter)

print("----------------")

att_counts = Counter(hero["primary_attr"]for hero in heroes)
print(att_counts)
print(att_counts)
print(att_counts.most_common(3))

print("----------------")

carry = [
    hero["localized_name"]
    for hero in heroes
    if "Carry" in hero["roles"]
]
carry.sort()
print(len(carry))
print(carry)


print("--------------")

def find_hero(query):
    result = []
    for hero in heroes:
        if query.lower() in hero["localized_name"].lower():
            result.append(hero)
    return result

print(find_hero("spirit"))