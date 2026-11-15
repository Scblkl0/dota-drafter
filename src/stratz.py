import os

import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("STRATZ_TOKEN")
if not token:
    raise RuntimeError("STRATZ_TOKEN is missing: create a .env file in the project root")

STRATZ_URL = "https://api.stratz.com/graphql"
GAME_VERSION_ID = 190      # patch 7.41f
GAME_MODE = 22             # Ranked All Pick
DEFAULT_RANK = 55          # Legend 5

DRAFT_QUERY = """
query Draft($request: PlusDraftRequestType!) {
  plus {
    draft(request: $request) {
      winValues
      players {
        slot
        position
        heroes {
          heroId
          letter
        }
      }
    }
  }
}
"""


def get_draft(radiant, dire):
    players = []

    for i in range(5):
        if i < len(radiant):
            hero_id = radiant[i]
        else:
            hero_id = None
        players.append({"slot": i, "heroId": hero_id, "rank": DEFAULT_RANK})

    for i in range(5):
        if i < len(dire):
            hero_id = dire[i]
        else:
            hero_id = None
        players.append({"slot": i + 5, "heroId": hero_id, "rank": DEFAULT_RANK})

    request = {
        "matchId": 0,
        "gameMode": GAME_MODE,
        "gameVersionId": GAME_VERSION_ID,
        "players": players,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "STRATZ_API",
    }

    response = requests.post(
        STRATZ_URL,
        json={"query": DRAFT_QUERY, "variables": {"request": request}},
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()

    result = response.json()
    if result.get("errors"):
        raise RuntimeError(f"Stratz returned an error: {result['errors']}")

    return result["data"]["plus"]["draft"]["players"]


if __name__ == "__main__":
    players = get_draft([1], [14])
    print(len(players))
    print(players[1]["slot"], players[1]["position"])
    print(players[1]["heroes"][:3])