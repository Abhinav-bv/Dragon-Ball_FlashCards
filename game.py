"""Game rules. Rarity is a local gameplay rule, not a canonical power ranking."""
import random
import re
from decimal import Decimal, InvalidOperation

TIERS = {"Common": (0, 50), "Rare": (3, 30), "Epic": (7, 14), "Legendary": (12, 5), "Mythic": (20, 1), "Unranked": (0, 50)}
UNITS = {"thousand": 3, "million": 6, "billion": 9, "trillion": 12,
         "quadrillion": 15, "quintillion": 18, "sextillion": 21,
         "septillion": 24, "septllion": 24, "octillion": 27}
MODES = ("Guess the warrior", "Race recall", "Alliance quiz")


def power(value):
    text = str(value).strip().lower()
    match = re.fullmatch(r"([0-9.,]+)\s*([a-z]*)", text)
    if not match:
        return None
    number, unit = match.groups()
    if unit and unit not in UNITS:
        return None
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number):
        number = number.replace(".", "").replace(",", "")
    elif "," in number:
        return None
    try:
        return Decimal(number) * (Decimal(10) ** UNITS.get(unit, 0))
    except InvalidOperation:
        return None


def rarity(value):
    amount = power(value)
    if amount is None:
        return "Unranked"
    for threshold, tier in [(24, "Mythic"), (18, "Legendary"), (12, "Epic"), (6, "Rare")]:
        if amount >= Decimal(10) ** threshold:
            return tier
    return "Common"


def requirement(form):
    return TIERS[rarity(form.get("ki"))][0]


def pull_groups(characters, owned):
    groups = {}
    for character in characters:
        if character["id"] not in owned:
            groups.setdefault(rarity(character.get("ki")), []).append(character)
    return groups


def draw(groups, rng=random):
    tiers = list(groups)
    tier = rng.choices(tiers, weights=[TIERS[t][1] for t in tiers], k=1)[0]
    return rng.choice(groups[tier])


def question(characters, mode, rng=random):
    if mode not in MODES:
        raise ValueError("Unknown game mode")
    field = {MODES[0]: "name", MODES[1]: "race", MODES[2]: "affiliation"}[mode]
    eligible = [c for c in characters if c.get(field) and (field != "name" or c.get("image"))]
    values = sorted({c[field] for c in eligible})
    if len(values) < 2:
        raise ValueError("This quiz needs at least two different answers in the roster.")
    target = rng.choice(eligible)
    correct = target[field]
    options = rng.sample([v for v in values if v != correct], min(3, len(values) - 1)) + [correct]
    rng.shuffle(options)
    prompt = {"name": "Who is this warrior?", "race": f"What race is {target['name']}?", "affiliation": f"Which affiliation does {target['name']} belong to?"}[field]
    return {"mode": mode, "prompt": prompt, "answer": correct, "options": options,
            "image": target.get("image") if field == "name" else None,
            "hint": f"Race: {target.get('race', 'Unknown')} | Affiliation: {target.get('affiliation', 'Unknown')}" if field == "name" else "Use the roster's race and affiliation labels.",
            "character": target["name"]}
