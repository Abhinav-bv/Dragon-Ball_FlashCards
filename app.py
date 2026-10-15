"""Dragon Ball FlashCards: play, summon, collect, and compare."""
import json
import random
import sqlite3
from pathlib import Path

import requests
import streamlit as st

import api
import game
import storage

st.set_page_config(page_title="Dragon Ball FlashCards", page_icon="🐉", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('style.css').read_text()}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def roster():
    return api.get_characters()


@st.cache_data(ttl=3600, show_spinner=False)
def detail(character_id):
    """Load character details, including the Vegeta Ego correction."""
    return api.get_character(character_id)


def card(character, key, wins):
    with st.container(border=True):
        st.subheader(character["name"])
        forms = [{"name": "Base form", "image": character.get("image"), "ki": character.get("ki")}]
        forms += character.get("transformations") or []
        def label(index):
            form = forms[index]
            tier = game.rarity(form.get("ki"))
            needed = game.requirement(form) if index else 0
            suffix = f"LOCKED · {needed} wins" if wins < needed else "Unlocked"
            return f"{form['name']} · {tier} · {suffix}"
        index = st.selectbox("Choose a form", range(len(forms)), format_func=label, key=f"{key}_form_{character['id']}")
        form = forms[index]
        required = game.requirement(form) if index else 0
        if wins < required:
            st.warning(f"Locked: earn {required - wins} more wins to unlock {form['name']}.")
            st.progress(min(wins / required, 1.0), text=f"{wins} / {required} total wins")
            st.caption(f"{game.rarity(form.get('ki'))} transformation · Wins are never spent.")
            return None
        st.caption(f"{game.rarity(form.get('ki')).upper()} · UNLOCKED")
        if api.image_url(form.get("image")):
            st.image(form["image"], width="stretch", alt=f"{character['name']} - {form['name']}")
        else:
            st.info("No image available for this form.")
        st.metric("Selected form Ki", api.display_value(form.get("ki")))
        a, b = st.columns(2)
        a.caption("RACE")
        a.write(character.get("race") or "Unknown")
        b.caption("AFFILIATION")
        b.write(character.get("affiliation") or "Unknown")
        with st.expander("Character details"):
            st.write(f"**Base Ki:** {api.display_value(character.get('ki'))}")
            st.write(f"**Maximum Ki:** {api.display_value(character.get('maxKi'))}")
            st.write(f"**Origin planet:** {(character.get('originPlanet') or {}).get('name') or 'Unknown'}")
            if character.get("description"):
                st.caption("Biography in the source's original language")
                st.write(character["description"])
    return {"character": character["name"], "form": form["name"], "rarity": game.rarity(form.get("ki")), "ki": form.get("ki")}


def play(characters):
    st.header("Training grounds")
    st.write("Every correct answer earns 1 win and 1 pull. Wrong answers cost nothing.")
    mode = st.selectbox("Mini-game", game.MODES)
    round_key = f"round_{mode}"
    current = storage.get_round(st.session_state.get(round_key, ""))
    if current is None:
        if st.button("Start challenge", type="primary"):
            try:
                st.session_state[round_key] = storage.new_round(game.question(characters, mode))
                st.rerun()
            except ValueError as exc:
                st.info(str(exc))
        return
    st.subheader(current["prompt"])
    if api.image_url(current.get("image")):
        st.image(current["image"], width=240, alt="Mystery warrior")
    with st.expander("Show a hint"):
        st.write(current["hint"])
    if current["won"] is None:
        answer = st.radio("Your answer", current["options"], index=None, key=f"answer_{current['id']}")
        if st.button("Submit answer", type="primary", disabled=answer is None):
            storage.submit(current["id"], answer)
            st.rerun()
    else:
        if current["won"]:
            st.success("Correct! +1 win and +1 pull added to your save.")
        else:
            st.error(f"The answer was {current['answer']}. Try another challenge!")
        if st.button("Next challenge", type="primary"):
            try:
                st.session_state[round_key] = storage.new_round(game.question(characters, mode))
                st.rerun()
            except ValueError as exc:
                st.info(str(exc))


def summon(characters, state):
    st.header("Summon a warrior")
    st.write("Spend 1 earned pull to unlock a new character's base form. No duplicates. Your first pull is free.")
    groups = game.pull_groups(characters, state["owned"])
    if not groups:
        st.success("You have collected the entire current roster! Keep playing to unlock transformations.")
    if st.button("Pull a character", type="primary", disabled=state["tickets"] < 1 or not groups):
        try:
            st.session_state.last_pull = storage.pull(characters)
            st.rerun()
        except ValueError as exc:
            st.info(str(exc))
    if state["tickets"] < 1 and groups:
        st.info("Head to Play and win a challenge to earn your next pull.")
    result = st.session_state.get("last_pull")
    if result:
        with st.container(border=True):
            st.caption("LATEST UNLOCK")
            st.subheader(result["name"])
            st.write(f"**{game.rarity(result.get('ki'))}** · Base form added to your collection")
            if api.image_url(result.get("image")):
                st.image(result["image"], width=260, alt=result["name"])
    if groups:
        with st.expander("Current pull odds"):
            total = sum(game.TIERS[t][1] for t in groups)
            for tier, pool in groups.items():
                st.write(f"**{tier}: {game.TIERS[tier][1] / total:.1%}** · {len(pool)} unowned characters")
            st.caption("First we draw a rarity tier, then a character uniformly within it. Empty tiers are removed and odds adjust as your collection grows.")


def collection(characters, state):
    st.header("Your collection")
    owned = state["owned"]
    st.progress(len(owned & {c['id'] for c in characters}) / len(characters), text=f"{len(owned)} characters collected")
    only_owned = st.checkbox("Show only unlocked characters")
    options = [c for c in characters if not only_owned or c["id"] in owned]
    if not options:
        st.info("Your collection is empty. Use your welcome pull in Summon.")
        return
    names = {c["id"]: c for c in options}
    ident = st.selectbox("Browse collection", list(names), format_func=lambda i: f"{names[i]['name']} · {'Unlocked' if i in owned else 'Locked'}")
    character = names[ident]
    if ident not in owned:
        st.warning(f"{character['name']} is locked. Unlock this character through Summon.")
        st.caption(f"Base rarity: {game.rarity(character.get('ki'))}")
    else:
        card(detail(ident), "collection", state["wins"])
    st.subheader("Transformation milestones")
    st.caption("Own the character first. Reaching a milestone unlocks every matching transformation in your collection automatically.")
    for tier in ["Rare", "Epic", "Legendary", "Mythic"]:
        required = game.TIERS[tier][0]
        st.write(f"{'✓' if state['wins'] >= required else '🔒'} **{tier}** · {required} total wins")
    if state["games"]:
        st.subheader("Training record")
        st.dataframe(state["games"], hide_index=True, width="stretch")


def compare(characters, state):
    st.header("Clash cards")
    available = [c for c in characters if c["id"] in state["owned"]]
    if len(available) < 2:
        st.info("Unlock at least two characters in Summon to compare them here.")
        return
    race = st.selectbox("Race filter", ["All races"] + sorted({c.get("race") for c in available if c.get("race")}))
    affiliation = st.selectbox("Affiliation filter", ["All affiliations"] + sorted({c.get("affiliation") for c in available if c.get("affiliation")}))
    available = [c for c in available if (race == "All races" or c.get("race") == race) and (affiliation == "All affiliations" or c.get("affiliation") == affiliation)]
    if len(available) < 2:
        st.info("Fewer than two unlocked characters match this filter.")
        return
    ids = [c["id"] for c in available]
    names = {c["id"]: c["name"] for c in available}
    for key, fallback in [("left_id", ids[0]), ("right_id", ids[1])]:
        if st.session_state.get(key) not in ids:
            st.session_state[key] = fallback
    if st.button("Random matchup"):
        st.session_state.left_id, st.session_state.right_id = random.sample(ids, 2)
    a, b = st.columns(2)
    with a:
        left = st.selectbox("First character", ids, format_func=names.get, key="left_id")
    with b:
        right = st.selectbox("Second character", ids, format_func=names.get, key="right_id")
    if left == right:
        st.info("Choose two different characters to compare.")
        return
    with a:
        first = card(detail(left), "left", state["wins"])
    with b:
        second = card(detail(right), "right", state["wins"])
    if first and second:
        st.download_button("Save matchup as JSON", json.dumps({"source": api.BASE_URL, "challengers": [first, second]}, indent=2), "dragon-ball-matchup.json", "application/json")


st.markdown('<div class="eyebrow">TRAIN · SUMMON · ASCEND</div>', unsafe_allow_html=True)
st.title("Dragon Ball FlashCards")
st.write("Build your collection. Earn your transformations.")
try:
    state = storage.progress()
    a, b, c = st.columns(3)
    a.metric("Total wins", state["wins"])
    b.metric("Available pulls", state["tickets"])
    c.metric("Characters unlocked", len(state["owned"]))
    with st.sidebar:
        page = st.radio("Go to", ["Play", "Summon", "Collection", "Compare"])
        st.caption("One local player · Progress saved on this computer")
        with st.expander("How progression works"):
            st.write("1. Start with one welcome pull.\n2. Every correct quiz answer earns one win and one pull.\n3. Pulls unlock new base characters.\n4. Wins unlock rarer forms of characters you own.")
            st.write("Rarity by source Ki: Common below 1 million; Rare from 1 million; Epic from 1 trillion; Legendary from 1 quintillion; Mythic from 1 septillion. Unknown values are Unranked.")
            st.caption("These are game rules, not official rarity or combat rankings. Common and Unranked forms unlock with their character. All pulls are earned through play.")
        st.link_button("Data source", "https://web.dragonball-api.com/documentation")
    with st.spinner("Loading the roster…"):
        characters = roster()
    if page == "Play":
        play(characters)
    elif page == "Summon":
        summon(characters, state)
    elif page == "Collection":
        collection(characters, state)
    else:
        compare(characters, state)
    st.caption("Unofficial fan project · Dragon Ball API data and artwork · Ki displayed as supplied by the source")
except (requests.RequestException, api.DataError):
    st.error("The character service is unavailable. Your saved collection is safe. Try again shortly.")
    if st.button("Try again"):
        roster.clear()
        detail.clear()
        st.rerun()
except sqlite3.Error:
    st.error("Your save could not be accessed. Check that the project's data folder is writable, then refresh.")
