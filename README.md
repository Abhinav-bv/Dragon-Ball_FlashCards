# Dragon Ball FlashCards

A solo Python and Streamlit collection game powered by the Dragon Ball API. Play short quizzes, earn pulls, collect characters, and unlock their transformations through cumulative wins.

## Play loop

1. Start with one free welcome pull in **Summon**.
2. Win **Guess the warrior**, **Race recall**, or **Alliance quiz** in **Play**. Each correct answer earns one win and one pull. Wrong answers cost nothing.
3. Spend one pull for a new character's base form. Pulls never produce duplicates, and no pull is spent if the roster is complete.
4. Inspect your characters and locked forms in **Collection**. Transformation milestones unlock automatically as your total wins grow.
5. Use **Compare** to compare two owned characters and their unlocked transformations, then export a matchup as JSON.

| Rarity | Source Ki threshold | Total wins to unlock a transformation |
| --- | --- | --- |
| Common | Below 1 million | 0, once character is owned |
| Rare | 1 million | 3 |
| Epic | 1 trillion | 7 |
| Legendary | 1 quintillion | 12 |
| Mythic | 1 septillion | 20 |
| Unranked | Unrecognized or missing value | 0, once character is owned |

These are local game rules, not official Dragon Ball rarity or battle rankings. Wins are cumulative and never spent. Base forms obtained through pulls are usable immediately regardless of their rarity. Higher-rarity transformations require the corresponding total wins and ownership of the character.

Pulls select an available rarity tier using relative weights of Common 50, Rare 30, Epic 14, Legendary 5, Mythic 1, and Unranked 50, then select uniformly within that tier's unowned characters. Empty tiers are excluded. The Summon page shows the current probabilities. No purchases or paid currency are involved.

## Run in Windows / VS Code

Open this folder in VS Code. The project uses Python 3.11.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed by Streamlit. Stop it with Ctrl+C. The existing `run.ps1` and VS Code launch configuration also start the app.

## Saved progress

`data/progress.sqlite3` stores wins, earned pulls, owned characters, and completed quiz results. It is a **single local player save shared by all browser sessions using this app instance**. Refreshing or restarting the app preserves it. Back up the data folder to retain progress; it is excluded from Git. This version is intended for local play, not competitive or multi-user hosting.

Quiz submission and reward updates run together in a SQLite transaction. A completed round cannot award another reward. Pull spending and character acquisition also run in one transaction, protecting the balance and preventing duplicate acquisitions.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary databases and mock character data. They cover power parsing, rarity milestones, persistence, reward replay, invalid answers, duplicate-free pulls, completed collections, transformation locks, playable UI flows, API pagination, and service failures. They never change your real save.

## Structure

- `app.py`: navigation, quizzes, collection cards, pulls, and comparisons
- `game.py`: Ki parsing, rarities, milestones, quiz generation, and weighted pulls
- `storage.py`: transactional SQLite persistence
- `api.py`: API requests, pagination, validation, and Vegeta Ego label correction
- `style.css` and `.streamlit/config.toml`: responsive dark theme
- `tests/test_project.py`: offline regression tests

## Data and limitations

The app needs internet access for character data and artwork. API responses are cached for one hour. Ki values are displayed as supplied; supported numeric formats are parsed only for gameplay rarity. Unrecognized values are explicitly Unranked. Descriptions remain in the source's original language.

Data and artwork are supplied by [Dragon Ball API](https://web.dragonball-api.com/). This is an unofficial fan project, not affiliated with Dragon Ball rights holders. No artwork is bundled in the repository.

## Resume description

Built a Python and Streamlit character-collection game integrating a public REST API, three quiz modes, weighted character pulls, and win-based transformation unlocks; implemented SQLite persistence, transactional rewards, cached requests, and automated progression tests.
