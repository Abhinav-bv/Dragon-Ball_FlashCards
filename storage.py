"""Transactional, local single-player save. Each quiz can award a reward only once."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

import game

DB_PATH = Path(__file__).parent / "data" / "progress.sqlite3"


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS player (id INTEGER PRIMARY KEY CHECK(id=1), wins INTEGER NOT NULL DEFAULT 0, tickets INTEGER NOT NULL DEFAULT 1 CHECK(tickets>=0));
        INSERT OR IGNORE INTO player(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS collection (character_id INTEGER PRIMARY KEY, name TEXT NOT NULL, rarity TEXT NOT NULL, acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS rounds (id TEXT PRIMARY KEY, mode TEXT NOT NULL, payload TEXT NOT NULL, submitted TEXT, won INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def progress():
    with connect() as db:
        state = dict(db.execute("SELECT wins,tickets FROM player WHERE id=1").fetchone())
        state["owned"] = {r["character_id"] for r in db.execute("SELECT character_id FROM collection")}
        state["games"] = [dict(r) for r in db.execute("SELECT mode, COUNT(*) AS played, SUM(won) AS wins FROM rounds WHERE won IS NOT NULL GROUP BY mode")]
        return state


def new_round(payload):
    ident = uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO rounds(id,mode,payload) VALUES(?,?,?)", (ident, payload["mode"], json.dumps(payload)))
    return ident


def get_round(ident):
    with connect() as db:
        row = db.execute("SELECT * FROM rounds WHERE id=?", (ident,)).fetchone()
        if row is None:
            return None
        result = json.loads(row["payload"])
        result.update(id=ident, submitted=row["submitted"], won=row["won"])
        return result


def submit(ident, answer):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT payload,won FROM rounds WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise ValueError("Round not found")
        if row["won"] is not None:
            return False
        payload = json.loads(row["payload"])
        if answer not in payload["options"]:
            raise ValueError("Choose one of the offered answers")
        won = int(answer == payload["answer"])
        db.execute("UPDATE rounds SET submitted=?,won=? WHERE id=?", (answer, won, ident))
        if won:
            db.execute("UPDATE player SET wins=wins+1,tickets=tickets+1 WHERE id=1")
        return True


def pull(characters):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        tickets = db.execute("SELECT tickets FROM player WHERE id=1").fetchone()[0]
        owned = {r[0] for r in db.execute("SELECT character_id FROM collection")}
        groups = game.pull_groups(characters, owned)
        if not groups:
            raise ValueError("You have collected the entire current roster. Your pulls are saved.")
        if tickets < 1:
            raise ValueError("Win a mini-game to earn your next pull.")
        character = game.draw(groups)
        db.execute("INSERT INTO collection(character_id,name,rarity) VALUES(?,?,?)", (character["id"], character["name"], game.rarity(character.get("ki"))))
        db.execute("UPDATE player SET tickets=tickets-1 WHERE id=1")
        return character
