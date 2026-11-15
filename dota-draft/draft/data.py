from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

APP_DIR = Path(os.environ.get("DRAFT_HELPER_DIR")
               or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DotaDraftHelper")
IMG_DIR = APP_DIR / "img"
SETTINGS_FILE = APP_DIR / "settings.json"
SETTINGS_BACKUP = APP_DIR / "settings.bak.json"

OPENDOTA = "https://api.opendota.com/api"
STEAM_CDN = "https://cdn.cloudflare.steamstatic.com"
STRATZ_URL = "https://api.stratz.com/graphql"

HEROES_TTL = 24 * 3600
MATCHUPS_TTL = 3 * 24 * 3600

BRACKETS = [
    ("All ranks", None, None, [1, 2, 3, 4, 5, 6, 7, 8]),
    ("Herald – Guardian", "HERALD_GUARDIAN", ["HERALD", "GUARDIAN"], [1, 2]),
    ("Crusader – Archon", "CRUSADER_ARCHON", ["CRUSADER", "ARCHON"], [3, 4]),
    ("Legend – Ancient", "LEGEND_ANCIENT", ["LEGEND", "ANCIENT"], [5, 6]),
    ("Divine – Immortal", "DIVINE_IMMORTAL", ["DIVINE", "IMMORTAL"], [7, 8]),
]

POS_NAMES = {1: "Carry", 2: "Mid", 3: "Offlane", 4: "Soft support", 5: "Hard support"}
POS_MIN_SHARE = 0.10


class DataError(Exception):
    pass


def _ensure_dirs():
    IMG_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    for f in (SETTINGS_FILE, SETTINGS_BACKUP):
        try:
            s = json.loads(f.read_text("utf-8"))
            if isinstance(s, dict):
                return s
        except Exception:
            continue
    return {}


def save_settings(s: dict):
    _ensure_dirs()
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), "utf-8")
    try:
        if SETTINGS_FILE.exists():
            os.replace(SETTINGS_FILE, SETTINGS_BACKUP)
    except OSError:
        pass
    os.replace(tmp, SETTINGS_FILE)


def _http(url: str, body: bytes | None = None, headers: dict | None = None, timeout=30) -> bytes:
    h = {"User-Agent": "DotaDraftHelper/1.0"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cache_read(name: str, ttl: float):
    p = APP_DIR / name
    try:
        if time.time() - p.stat().st_mtime < ttl:
            return json.loads(p.read_text("utf-8"))
    except Exception:
        pass
    return None


def _cache_read_stale(name: str):
    try:
        return json.loads((APP_DIR / name).read_text("utf-8"))
    except Exception:
        return None


def _cache_write(name: str, obj):
    _ensure_dirs()
    (APP_DIR / name).write_text(json.dumps(obj), "utf-8")


def load_heroes() -> list[dict]:
    raw = _cache_read("heroes.json", HEROES_TTL)
    if raw is None:
        try:
            raw = json.loads(_http(f"{OPENDOTA}/heroStats"))
            _cache_write("heroes.json", raw)
        except Exception as e:
            raw = _cache_read_stale("heroes.json")
            if raw is None:
                raise DataError(f"Could not load the hero list: {e}")
    heroes = []
    for h in raw:
        heroes.append({
            "id": h["id"],
            "short": h["name"].replace("npc_dota_hero_", ""),
            "name": h["localized_name"],
            "roles": h.get("roles", []),
            "cm": bool(h.get("cm_enabled", True)),
            "img": h["img"].rstrip("?"),
            "wr": {r: (h.get(f"{r}_pick", 0), h.get(f"{r}_win", 0)) for r in range(1, 9)},
        })
    heroes.sort(key=lambda x: x["name"])
    return heroes


def hero_winrate(hero: dict, ranks: list[int]) -> float | None:
    pick = sum(hero["wr"][r][0] for r in ranks)
    win = sum(hero["wr"][r][1] for r in ranks)
    return 100.0 * win / pick if pick else None


def img_path(hero: dict) -> Path:
    return IMG_DIR / f"{hero['short']}.png"


def download_images(heroes: list[dict], progress=None):
    _ensure_dirs()
    todo = [h for h in heroes if not img_path(h).exists()]
    if not todo:
        return
    done = 0

    def one(h):
        try:
            img_path(h).write_bytes(_http(STEAM_CDN + h["img"]))
        except Exception:
            pass

    with ThreadPoolExecutor(8) as ex:
        for _ in ex.map(one, todo):
            done += 1
            if progress:
                progress(done, len(todo), "Downloading hero portraits")


ITEMS_TTL = 7 * 24 * 3600
BUILD_TTL = 3 * 24 * 3600
ITEM_DIR = IMG_DIR / "items"
BUILD_SECTIONS = [("start_game_items", "START"), ("early_game_items", "EARLY"),
                  ("mid_game_items", "MID"), ("late_game_items", "LATE")]
BUILD_TOP = 6


def load_items() -> dict[int, dict]:
    raw = _cache_read("items.json", ITEMS_TTL)
    if raw is None:
        try:
            raw = json.loads(_http(f"{OPENDOTA}/constants/items"))
            _cache_write("items.json", raw)
        except Exception as e:
            raw = _cache_read_stale("items.json")
            if raw is None:
                raise DataError(f"Could not load the item list: {e}")
    out = {}
    for key, it in raw.items():
        if it.get("id") is None or key.startswith("recipe"):
            continue
        out[it["id"]] = {"key": key, "name": it.get("dname") or key, "img": (it.get("img") or "").split("?")[0],
                         "assembled": bool(it.get("components")), "cost": it.get("cost") or 0,
                         "components": list(it.get("components") or [])}
    return out


def item_icon(item: dict) -> Path:
    return ITEM_DIR / f"{item['key']}.png"


def _build_file(hero_id: int) -> str:
    return f"build_{hero_id}.json"


def _build_raw(hero_id: int) -> dict:
    raw = _cache_read(_build_file(hero_id), BUILD_TTL)
    if raw is not None:
        return raw
    for attempt in range(5):
        try:
            raw = json.loads(_http(f"{OPENDOTA}/heroes/{hero_id}/itemPopularity"))
            _cache_write(_build_file(hero_id), raw)
            return raw
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 + 4 * attempt)
                continue
            break
        except Exception:
            time.sleep(2)
    raw = _cache_read_stale(_build_file(hero_id))
    if raw is None:
        raise DataError("Could not load the item build from OpenDota")
    return raw


MID_MIN_COST = 900


def _is_boots(it: dict) -> bool:
    return any(w in it["name"] for w in ("Boots", "Treads", "Greaves"))


def _item_sections(start: dict[int, int], mid: dict[int, int], late: dict[int, int],
                   items: dict[int, dict]) -> list[tuple[str, list[dict]]]:
    ITEM_DIR.mkdir(parents=True, exist_ok=True)
    total: dict[str, int] = {}
    for counts in (mid, late):
        for iid, count in counts.items():
            if iid in items:
                k = items[iid]["key"]
                total[k] = max(total.get(k, 0), count)
    parts = set()
    for it in items.values():
        n = total.get(it["key"], 0)
        for c in it["components"]:
            if n and n >= 0.5 * total.get(c, 0):
                parts.add(c)

    def row(iid, count):
        it = items[iid]
        return {"id": iid, "name": it["name"], "count": count, "icon": str(item_icon(it)), "_it": it}

    def candidates(counts):
        out = []
        for iid, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            it = items.get(iid)
            if not it or not it["assembled"] or it["key"] in parts:
                continue
            if it["cost"] < MID_MIN_COST and not _is_boots(it):
                continue
            out.append((iid, count))
        return out

    start_rows = [row(i, c) for i, c in sorted(start.items(), key=lambda kv: -kv[1]) if i in items][:BUILD_TOP]
    mid_c, late_c = candidates(mid), candidates(late)
    boots = [x for x in mid_c if _is_boots(items[x[0]])][:2]
    mid_c = boots + [x for x in mid_c if x not in boots]
    shown, mid_rows, late_rows, rest = set(), [], [], []
    for iid, c in mid_c:
        if iid in shown:
            continue
        (mid_rows if len(mid_rows) < BUILD_TOP else rest).append((iid, c))
        shown.add(iid)
    for iid, c in late_c:
        if iid in shown:
            continue
        (late_rows if len(late_rows) < BUILD_TOP else rest).append((iid, c))
        shown.add(iid)
    rest.sort(key=lambda x: -x[1])
    out = [("STARTING ITEMS", start_rows), ("MID GAME", [row(i, c) for i, c in mid_rows]),
           ("LATE GAME", [row(i, c) for i, c in late_rows]),
           ("ALSO POPULAR", [row(i, c) for i, c in rest[:BUILD_TOP]])]
    for _, rows in out:
        for r in rows:
            it = r.pop("_it")
            p = item_icon(it)
            if not p.exists() and it["img"]:
                try:
                    p.write_bytes(_http(STEAM_CDN + it["img"]))
                except Exception:
                    pass
    return out


def load_build(hero_id: int, items: dict[int, dict] | None = None) -> list[tuple[str, list[dict]]]:
    items = items or load_items()
    raw = _build_raw(hero_id)
    st = {key: {int(k): v for k, v in (raw.get(key) or {}).items()} for key, _ in BUILD_SECTIONS}
    mid = dict(st["early_game_items"])
    for iid, n in st["mid_game_items"].items():
        mid[iid] = max(mid.get(iid, 0), n)
    return _item_sections(st["start_game_items"], mid, st["late_game_items"], items)


ABILITY_DIR = IMG_DIR / "abilities"
TALENT_LEVELS = [10, 15, 20, 25]


def load_stratz_build(hero_id: int, bracket_idx: int, pos: int | None, token: str,
                      items: dict[int, dict] | None = None) -> dict:
    if not token:
        raise DataError("Stratz needs an API token")
    raw = _stratz_build_raw(hero_id, bracket_idx, pos, token)
    items = items or load_items()
    stats = raw.get("heroStats") or {}
    hero = (raw.get("constants") or {}).get("hero") or {}
    sections, start = _stratz_items(raw, items)

    def big(s):
        return sum(len(rows) for _, rows in s[1:])

    scope = (bracket_idx, pos)
    if big(sections) < BUILD_MIN_ITEMS:
        for b, p in [(bracket_idx, None), (0, pos), (0, None)]:
            if (b, p) == (bracket_idx, pos):
                continue
            try:
                wider, wstart = _stratz_items(_stratz_build_raw(hero_id, b, p, token), items)
            except DataError:
                continue
            if big(wider) > big(sections):
                if sections[0][1]:
                    wider[0] = sections[0]
                sections, scope = wider, (b, p)
            if big(sections) >= BUILD_MIN_ITEMS:
                break
    return _stratz_finish(raw, stats, hero, sections, start, scope)


BUILD_MIN_ITEMS = 8


def _stratz_build_raw(hero_id: int, bracket_idx: int, pos: int | None, token: str) -> dict:
    name = f"sbuild2_{hero_id}_{bracket_idx}_{pos or 0}.json"
    raw = _cache_read(name, BUILD_TTL)
    if raw is None:
        basic = BRACKETS[bracket_idx][1]
        args = f"heroId: {hero_id}"
        if basic:
            args += f", bracketBasicIds: [{basic}]"
        if pos:
            args += f", positionIds: [POSITION_{pos}]"
        q = ("{ heroStats { "
             f"talent({args}) {{ abilityId matchCount winCount }} "
             f"abilityMaxLevel({args}) {{ abilityId level matchCount }} "
             f"itemStartingPurchase({args}) {{ itemId wasGiven matchCount }} "
             f"itemFullPurchase({args}) {{ itemId instance time matchCount }} "
             f"itemBootPurchase({args}) {{ itemId instance matchCount }} "
             "} constants { hero(id: %d) { talents { abilityId slot } abilities { slot abilityId "
             "ability { name language { displayName } stat { isUltimate isInnate } } } } } }" % hero_id)
        raw = _stratz(q, token)
        tal = [t["abilityId"] for t in ((raw.get("constants") or {}).get("hero") or {}).get("talents") or []]
        if tal:
            q2 = "{ constants { " + " ".join(
                f"t{a}: ability(id: {a}) {{ language {{ displayName }} }}" for a in tal) + " } }"
            try:
                raw["talent_names"] = {k[1:]: ((v or {}).get("language") or {}).get("displayName")
                                       for k, v in (_stratz(q2, token).get("constants") or {}).items()}
            except DataError:
                raw["talent_names"] = {}
        _cache_write(name, raw)
    return raw


def _stratz_items(raw: dict, items: dict[int, dict]):
    stats = raw.get("heroStats") or {}
    start: dict[int, int] = {}
    for r in stats.get("itemStartingPurchase") or []:
        if not r.get("wasGiven"):
            start[r["itemId"]] = start.get(r["itemId"], 0) + (r.get("matchCount") or 0)
    cnt: dict[int, int] = {}
    tsum: dict[int, float] = {}
    for r in stats.get("itemFullPurchase") or []:
        if r.get("instance"):
            continue
        n = r.get("matchCount") or 0
        cnt[r["itemId"]] = cnt.get(r["itemId"], 0) + n
        tsum[r["itemId"]] = tsum.get(r["itemId"], 0.0) + n * (r.get("time") or 0)
    mid, late = {}, {}
    for iid, n in cnt.items():
        if "lotus" in (items.get(iid) or {}).get("name", "").lower():
            continue
        minute = tsum[iid] / n if n else 0
        (mid if minute < 27 else late)[iid] = n
    boots: dict[int, int] = {}
    for r in stats.get("itemBootPurchase") or []:
        if not r.get("instance"):
            boots[r["itemId"]] = boots.get(r["itemId"], 0) + (r.get("matchCount") or 0)
    for iid, n in boots.items():
        if n >= 0.2 * max(boots.values()):
            mid[iid] = max(mid.get(iid, 0), n)
    return _item_sections(start, mid, late, items), start


def _stratz_finish(raw: dict, stats: dict, hero: dict, sections: list, start: dict, scope: tuple) -> dict:
    basic_ids = {}
    for a in hero.get("abilities") or []:
        ab = a.get("ability") or {}
        st = ab.get("stat") or {}
        if ab.get("name") and not st.get("isUltimate") and not st.get("isInnate"):
            basic_ids[a["abilityId"]] = ab
    lv_n: dict[int, int] = {}
    lv_s: dict[int, float] = {}
    for r in stats.get("abilityMaxLevel") or []:
        a, n = r.get("abilityId"), r.get("matchCount") or 0
        if a in basic_ids:
            lv_n[a] = lv_n.get(a, 0) + n
            lv_s[a] = lv_s.get(a, 0.0) + n * (r.get("level") or 0)
    top = max(lv_n.values(), default=0)
    order = sorted((a for a in lv_n if lv_n[a] >= 0.25 * top), key=lambda a: lv_s[a] / lv_n[a])
    ABILITY_DIR.mkdir(parents=True, exist_ok=True)
    skills = []
    for a in order[:4]:
        ab = basic_ids[a]
        p = ABILITY_DIR / f"{ab['name']}.png"
        if not p.exists():
            try:
                p.write_bytes(_http(f"{STEAM_CDN}/apps/dota2/images/dota_react/abilities/{ab['name']}.png"))
            except Exception:
                pass
        skills.append({"name": (ab.get("language") or {}).get("displayName") or ab["name"], "icon": str(p)})

    picked = {r["abilityId"]: r.get("matchCount") or 0 for r in stats.get("talent") or []}
    names = raw.get("talent_names") or {}
    by_level: dict[int, list] = {}
    for t in hero.get("talents") or []:
        by_level.setdefault(t["slot"] // 2, []).append(t["abilityId"])
    talents = []
    for i, level in enumerate(TALENT_LEVELS):
        pair = [a for a in by_level.get(i, []) if names.get(str(a))]
        if not pair:
            continue
        best = max(pair, key=lambda a: picked.get(a, 0))
        tot = sum(picked.get(a, 0) for a in pair)
        share = 100.0 * picked.get(best, 0) / tot if len(pair) == 2 and tot else None
        talents.append((level, names[str(best)], share))
    return {"items": sections, "skills": skills, "talents": talents,
            "matches": max(start.values(), default=0), "items_scope": scope}


def builds_missing(heroes: list[dict]) -> list[dict]:
    out = []
    for h in heroes:
        try:
            fresh = time.time() - (APP_DIR / _build_file(h["id"])).stat().st_mtime < BUILD_TTL
        except OSError:
            fresh = False
        if not fresh:
            out.append(h)
    return out


def preload_builds(heroes: list[dict], progress=None):
    todo = builds_missing(heroes)
    items = load_items()
    for i, h in enumerate(todo):
        try:
            load_build(h["id"], items)
        except DataError:
            pass
        if progress:
            progress(i + 1, len(todo), "builds")
        time.sleep(1.05)


def _stratz(query: str, token: str) -> dict:
    try:
        resp = _http(STRATZ_URL, json.dumps({"query": query}).encode(), {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "STRATZ_API",
        })
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            raise DataError("Stratz rejected the token — check it in Settings")
        if e.code == 429:
            raise DataError("Stratz rate limit reached — try again in a minute")
        raise DataError(f"Stratz returned error {e.code}: {detail}")
    except Exception as e:
        raise DataError(f"Stratz is unreachable: {e}")
    data = json.loads(resp)
    if data.get("errors"):
        raise DataError("Stratz: " + str(data["errors"][0].get("message", data["errors"]))[:300])
    return data.get("data") or {}


def check_stratz_token(token: str) -> tuple[bool, str]:
    token = token.strip()
    if not token:
        return False, "Paste your token first."
    try:
        _http(STRATZ_URL, json.dumps({"query": "{ __typename }"}).encode(), {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "STRATZ_API",
        }, timeout=15)
        return True, "Connected"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "Stratz rejected this token. Copy it again from stratz.com/api."
        if e.code == 429:
            return False, "Stratz rate limit reached. Wait a minute and try again."
        return True, "Connected"
    except Exception as e:
        return False, f"Could not reach Stratz: {e}"


def _matchups_file(source: str, bracket_idx: int) -> str:
    return f"matchups_stratz_v2_{bracket_idx}.json" if source == "stratz" else "matchups_opendota.json"


def preload_jobs(use_stratz: bool, heroes: list[dict] | None = None) -> list[tuple[str, int]]:
    jobs = [("stratz", i) for i in range(len(BRACKETS))] if use_stratz else []
    jobs.append(("opendota", 0))
    out = []
    for src, idx in jobs:
        p = APP_DIR / _matchups_file(src, idx)
        try:
            fresh = time.time() - p.stat().st_mtime < MATCHUPS_TTL
        except OSError:
            fresh = False
        if not fresh:
            out.append((src, idx))
    if heroes and builds_missing(heroes):
        out.append(("builds", 0))
    return out


def load_matchups(source: str, bracket_idx: int, heroes: list[dict], token: str = "",
                  progress=None, force=False) -> dict:
    name = _matchups_file(source, bracket_idx)
    m = None if force else _cache_read(name, MATCHUPS_TTL)
    if m is None:
        try:
            if source == "stratz":
                m = _fetch_stratz(heroes, bracket_idx, token, progress)
            else:
                m = _fetch_opendota(heroes, progress)
            _cache_write(name, m)
        except DataError:
            m = _cache_read_stale(name)
            if m is None:
                raise
    out = _intkeys(m)
    if not out["pos"]:
        out["pos"] = estimate_positions(heroes)
        out["pos_real"] = False
    else:
        out["pos_real"] = True
    return out


def _intkeys(m: dict) -> dict:
    out = {"source": m.get("source", "")}
    for k in ("vs", "with", "pos"):
        out[k] = {int(a): {int(b): v for b, v in d.items()} for a, d in (m.get(k) or {}).items()}
    return out


def estimate_positions(heroes: list[dict]) -> dict:
    out = {}
    for h in heroes:
        r = set(h["roles"])
        sup = "Support" in r
        p = set()
        if "Carry" in r and not sup:
            p.add(1)
        if "Nuker" in r and not sup:
            p.add(2)
        if r & {"Durable", "Initiator"} and not sup:
            p.add(3)
        if sup:
            p.add(4)
            if "Carry" not in r:
                p.add(5)
        if not p:
            p = {1, 2, 3, 4, 5}
        out[h["id"]] = {x: [0, 0] for x in p}
    return out


def _fetch_opendota(heroes, progress) -> dict:
    raw = {}
    n = len(heroes)
    for i, h in enumerate(heroes):
        for attempt in range(6):
            try:
                raw[h["id"]] = json.loads(_http(f"{OPENDOTA}/heroes/{h['id']}/matchups"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(10 + 5 * attempt)
                    continue
                raise DataError(f"OpenDota returned error {e.code}")
            except Exception as e:
                if attempt == 5:
                    raise DataError(f"OpenDota is unreachable: {e}")
                time.sleep(2)
        else:
            raise DataError("OpenDota rate limit reached, try again later")
        if progress:
            progress(i + 1, n, "Loading OpenDota stats (once, then cached)")
        time.sleep(1.05)

    base = {}
    for a, rows in raw.items():
        g = sum(r["games_played"] for r in rows)
        w = sum(r["wins"] for r in rows)
        base[a] = w / g if g else 0.5
    vs = {}
    for a, rows in raw.items():
        d = {}
        for r in rows:
            b, g = r["hero_id"], r["games_played"]
            if not g:
                continue
            expected = 0.5 + base[a] - base.get(b, 0.5)
            adv = (r["wins"] / g - expected) * 100.0
            d[b] = round(adv * g / (g + 40.0), 3)
        vs[a] = d
    return {"vs": vs, "with": {}, "pos": {}, "source": "opendota"}


def _fetch_stratz(heroes, bracket_idx: int, token: str, progress) -> dict:
    if not token:
        raise DataError("Stratz needs an API token — add it in Settings")
    basic, detailed = BRACKETS[bracket_idx][1], BRACKETS[bracket_idx][2]
    args = "take: 200"
    if basic:
        args += f", bracketBasicIds: [{basic}]"
    fields = "{ heroId vs { heroId2 synergy matchCount } with { heroId2 synergy matchCount } }"
    ids = [h["id"] for h in heroes]
    vs, wi = {}, {}
    step = 12
    for i in range(0, len(ids), step):
        chunk = ids[i:i + step]
        q = "{ heroStats { " + " ".join(
            f"h{hid}: matchUp(heroId: {hid}, {args}) {fields}" for hid in chunk) + " } }"
        stats = _stratz(q, token).get("heroStats") or {}
        for hid in chunk:
            entry = stats.get(f"h{hid}")
            if isinstance(entry, list):
                entry = entry[0] if entry else None
            if not entry:
                continue
            vs[hid] = {r["heroId2"]: round(float(r.get("synergy") or 0), 3) for r in entry.get("vs") or []}
            wi[hid] = {r["heroId2"]: round(float(r.get("synergy") or 0), 3) for r in entry.get("with") or []}
        if progress:
            progress(min(i + step, len(ids)), len(ids), "Loading Stratz stats")
        time.sleep(0.3)
    if not vs:
        raise DataError("Stratz returned an empty answer")

    pos = {}
    try:
        br = f", bracketIds: [{', '.join(detailed)}]" if detailed else ""
        q = "{ heroStats { " + " ".join(
            f"p{p}: winWeek(take: 4, positionIds: [POSITION_{p}]{br}) {{ heroId matchCount winCount }}"
            for p in range(1, 6)) + " } }"
        stats = _stratz(q, token).get("heroStats") or {}
        for p in range(1, 6):
            for r in stats.get(f"p{p}") or []:
                cell = pos.setdefault(r["heroId"], {}).setdefault(p, [0, 0])
                cell[0] += r.get("matchCount") or 0
                cell[1] += r.get("winCount") or 0
    except DataError:
        pos = {}
    return {"vs": vs, "with": wi, "pos": pos, "source": "stratz"}
