from __future__ import annotations

from .data import POS_MIN_SHARE

LANE_OPPONENTS = {1: {3, 4}, 5: {3, 4}, 2: {2}, 3: {1, 5}, 4: {1, 5}}
LANE_PARTNER = {1: 5, 5: 1, 3: 4, 4: 3}
LANE_WEIGHT = 1.5
POS_WR_WEIGHT = 0.5


def viable_positions(hid: int, pos: dict) -> dict[int, float | None]:
    table = pos.get(hid) or {}
    total = sum(v[0] for v in table.values())
    out = {}
    for p, (n, w) in table.items():
        if total == 0:
            out[p] = None
        elif n / total >= POS_MIN_SHARE:
            out[p] = 100.0 * w / n if n else None
    return out


def _score(cand, p, against, together, m, against_pos, together_pos):
    vs = m["vs"].get(cand, {})
    wi = m["with"].get(cand, {})
    parts_vs, parts_with, total = [], [], 0.0
    for e in against:
        v = vs.get(e, 0.0)
        w = LANE_WEIGHT if p and against_pos.get(e) in LANE_OPPONENTS[p] else 1.0
        parts_vs.append((e, v))
        total += v * w
    for a in together:
        v = wi.get(a, 0.0)
        w = LANE_WEIGHT if p and LANE_PARTNER.get(p) == together_pos.get(a) else 1.0
        parts_with.append((a, v))
        total += v * w
    return total, parts_vs, parts_with


def recommend(heroes, m, allies, enemies, bans, ally_pos=None, enemy_pos=None,
              cm_only=False, only_pos=None, pool=None) -> list[dict]:
    ally_pos, enemy_pos = ally_pos or {}, enemy_pos or {}
    taken = set(allies) | set(enemies) | set(bans)
    open_pos = set(range(1, 6)) - {ally_pos[a] for a in allies if a in ally_pos}
    if only_pos:
        open_pos &= {only_pos}
    out = []
    for h in heroes:
        if h["id"] in taken or (cm_only and not h["cm"]):
            continue
        if pool is not None and h["id"] not in pool:
            continue
        best = None
        for p, wr in viable_positions(h["id"], m["pos"]).items():
            if p not in open_pos:
                continue
            total, pv, pw = _score(h["id"], p, enemies, allies, m, enemy_pos, ally_pos)
            total += POS_WR_WEIGHT * (wr - 50.0) if wr is not None else 0.0
            if best is None or total > best["score"]:
                best = {"hero": h, "score": total, "pos": p, "pos_wr": wr, "vs": pv, "with": pw}
        if best:
            out.append(best)
    out.sort(key=lambda r: -r["score"])
    return out


def recommend_bans(heroes, m, allies, enemies, bans, ally_pos=None, enemy_pos=None,
                   cm_only=False) -> list[dict]:
    ally_pos, enemy_pos = ally_pos or {}, enemy_pos or {}
    taken = set(allies) | set(enemies) | set(bans)
    open_pos = set(range(1, 6)) - {enemy_pos[e] for e in enemies if e in enemy_pos}
    out = []
    for h in heroes:
        if h["id"] in taken or (cm_only and not h["cm"]):
            continue
        best = None
        for p, wr in viable_positions(h["id"], m["pos"]).items():
            if p not in open_pos:
                continue
            total, pv, pw = _score(h["id"], p, allies, enemies, m, ally_pos, enemy_pos)
            total += POS_WR_WEIGHT * (wr - 50.0) if wr is not None else 0.0
            if best is None or total > best["score"]:
                best = {"hero": h, "score": total, "pos": p, "pos_wr": wr, "vs": pv, "with": pw}
        if best:
            out.append(best)
    out.sort(key=lambda r: -r["score"])
    return out
