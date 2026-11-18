# Dota Draft Helper

A draft assistant for Dota 2 on Windows. During hero selection it reads the picks from the screen, suggests who to pick and who to ban, and after the draft shows a build for your hero.

## Features

**Draft**
- Automatic reading of both teams' picks from the hero selection screen (All Pick).
- Pick suggestions: advantage against enemy heroes and synergy with allies.
- Ban suggestions: the heroes most dangerous to your team.
- Positions 1–5 for any hero: taken positions are excluded from suggestions, and lane matchups get more weight.
- The best position for each suggested hero and its win rate there.
- Personal hero pool: suggestions only from the heroes you play.
- Manual mode: build a draft with clicks, without the game.

**Build after the draft**
- Items by stage: starting, mid game, late game and other popular items.
- The order in which abilities are usually maxed.
- Talents with the share of players choosing each option.
- Your hero is locked for the whole match; the data follows your rank and position.

**Overlay**
- A compact panel on top of the game: picks and bans during the draft, the build afterwards.
- Switches from draft to build by itself; build sections can be collapsed.

## Data sources

| Source | What it gives | What it needs |
|---|---|---|
| [OpenDota](https://www.opendota.com/) | Hero matchups, popular items | Nothing, works out of the box |
| [Stratz](https://stratz.com/) | Matchups and synergy by rank, win rates by position, skill order, talents, items by rank and position | A free personal token from [stratz.com/api](https://stratz.com/api) |

Without a Stratz token the program runs on OpenDota: no rank split, no skill order or talents, and hero positions are only estimated.

## Requirements

- Windows 10 or 11, 64-bit.
- Dota 2 in Borderless Window mode. Exclusive fullscreen cannot be read.
- Internet access to download statistics.

## Installation

### Installer

If `DotaDraftHelper-Setup-x.y.z.exe` is published under Releases, download and run it. No administrator rights are needed.

The installer is not signed, so Windows shows an "Unknown publisher" warning: click "More info" → "Run anyway". On computers with Smart App Control turned on, an unsigned installer is blocked — run from source instead.

### From source

You need [Python 3](https://www.python.org/downloads/) with the Python Launcher (`py`) installed.

1. Download the repository.
2. Run `dota-draft\run.bat`.

On the first run the script creates an environment, installs the dependencies (PySide6, NumPy, OpenCV) and starts the program.

## First-time setup

On the first run a **Setup** window opens with a checklist; you can reopen it later with the Setup button.

1. **Statistics and images** — downloaded automatically; the first time takes a few minutes.
2. **Game link file** — the program places a small file in the Dota 2 folder by itself.
3. **Launch option** — the only manual step. In Steam: right-click Dota 2 → Properties → General → Launch Options, add `-gamestateintegration` and restart Dota.
4. **Stratz** (optional) — paste your token.

Dota sends nothing to the program while you are in the main menu: the signal appears when a match starts. You can test the setup in a bot match.

## How it works

- **Game stage.** The program uses Game State Integration, a built-in Dota 2 feature through which the game itself reports the match stage, your side and your hero. The game does not report the enemy draft to a player.
- **Picks.** That is why heroes are read from the screen: the program captures the top strip of the Dota window and compares the ten slots with hero portraits. The screen is read only during hero selection.
- **Game memory** is never read, and the program does not touch the game process.
- **Resolution.** The window size is detected automatically. For 16:9 a measured layout is used; for other shapes the program finds the scale at the first pick.

## Limitations

- Automatic reading is built for the All Pick screen. Captains Mode uses a different draft screen, so only manual input works there.
- Bans are not read from the screen.
- If you start the program after the draft is over, it will not pick up that match's heroes.
- Screen shapes other than 16:9 were tested on simulated frames only.
- Stratz returns item statistics only for purchases that are common enough. For rare rank and position combinations items come from a wider sample, and the build says so.

## Where data is stored

Settings, the Stratz token and downloaded statistics are kept in `%LOCALAPPDATA%\DotaDraftHelper` on your computer. The token is sent nowhere except Stratz.
