from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QObject, Signal

PORT = 53917
CFG_NAME = "gamestate_integration_drafthelper.cfg"
CFG_TEXT = f'''"Dota Draft Helper"
{{
    "uri"       "http://127.0.0.1:{PORT}/"
    "timeout"   "5.0"
    "buffer"    "0.1"
    "throttle"  "0.5"
    "heartbeat" "5.0"
    "data"
    {{
        "provider" "1"
        "map"      "1"
        "player"   "1"
        "hero"     "1"
    }}
}}
'''
LAUNCH_OPTION = "-gamestateintegration"

PICK_STATES = {"DOTA_GAMERULES_STATE_HERO_SELECTION", "DOTA_GAMERULES_STATE_STRATEGY_TIME"}
SCAN_STATES = PICK_STATES | {"DOTA_GAMERULES_STATE_TEAM_SHOWCASE", "DOTA_GAMERULES_STATE_PRE_GAME",
                             "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"}
BUILD_STATES = {"DOTA_GAMERULES_STATE_STRATEGY_TIME", "DOTA_GAMERULES_STATE_TEAM_SHOWCASE",
                "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD", "DOTA_GAMERULES_STATE_PRE_GAME",
                "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"}
STATE_NAMES = {
    "DOTA_GAMERULES_STATE_WAIT_FOR_PLAYERS_TO_LOAD": "players loading",
    "DOTA_GAMERULES_STATE_HERO_SELECTION": "hero selection",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME": "strategy time",
    "DOTA_GAMERULES_STATE_TEAM_SHOWCASE": "team showcase",
    "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD": "map loading",
    "DOTA_GAMERULES_STATE_PRE_GAME": "pre-game",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS": "game in progress",
    "DOTA_GAMERULES_STATE_POST_GAME": "post-game",
}


def parse(payload: dict) -> dict:
    m = payload.get("map") or {}
    player = payload.get("player") or {}
    hero = payload.get("hero") or {}
    team = player.get("team_name")
    return {
        "in_game": bool(m),
        "state": m.get("game_state"),
        "matchid": str(m.get("matchid") or "") or None,
        "team": team if team in ("radiant", "dire") else None,
        "hero_id": hero.get("id") if isinstance(hero.get("id"), int) and hero.get("id") > 0 else None,
    }


class GsiServer(QObject):
    updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.info: dict | None = None
        self.last_time = 0.0
        self.error: str | None = None
        self._httpd = None

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    n = min(int(self.headers.get("Content-Length") or 0), 1 << 20)
                    info = parse(json.loads(self.rfile.read(n) or b"{}"))
                    outer.info, outer.last_time = info, time.time()
                    outer.updated.emit(info)
                except Exception:
                    pass
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError as e:
            self.error = f"port {PORT} is busy ({e})"
            return
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None

    def connected(self) -> bool:
        return time.time() - self.last_time < 30


def _steam_dir() -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except Exception:
        return None


def launch_option_set() -> bool | None:
    steam = _steam_dir()
    if not steam:
        return None
    found = None
    try:
        files = list((steam / "userdata").glob("*/config/localconfig.vdf"))
    except Exception:
        return None
    for f in files:
        try:
            text = f.read_text("utf-8", "replace")
        except Exception:
            continue
        for m in re.finditer(r'"570"\s*\{', text):
            depth, i = 1, m.end()
            while i < len(text) and depth:
                c = text[i]
                if c == '"':
                    i += 1
                    while i < len(text) and text[i] != '"':
                        i += 2 if text[i] == "\\" else 1
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                i += 1
            opt = re.search(r'"LaunchOptions"\s+"((?:[^"\\]|\\.)*)"', text[m.end():i])
            if opt is not None:
                if LAUNCH_OPTION in opt.group(1):
                    return True
                found = False
            elif found is None and '"LastPlayed"' in text[m.end():i]:
                found = False
    return found


def find_cfg_dir() -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except Exception:
        return None
    libs = [steam]
    try:
        text = (steam / "steamapps" / "libraryfolders.vdf").read_text("utf-8", "replace")
        libs += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    except Exception:
        pass
    for lib in libs:
        cfg = lib / "steamapps" / "common" / "dota 2 beta" / "game" / "dota" / "cfg"
        if cfg.is_dir():
            return cfg
    return None


def cfg_file(cfg_dir: Path) -> Path:
    return cfg_dir / "gamestate_integration" / CFG_NAME


def is_installed(cfg_dir: Path | None) -> bool:
    return bool(cfg_dir) and cfg_file(cfg_dir).exists()


def install(cfg_dir: Path):
    f = cfg_file(cfg_dir)
    f.parent.mkdir(exist_ok=True)
    f.write_text(CFG_TEXT, "utf-8")
