"""Small, independently testable client for the public Dragon Ball API."""
from urllib.parse import urlparse
import requests

BASE_URL = "https://dragonball-api.com/api"


class DataError(ValueError):
    """The service returned a response the app cannot safely use."""


def _get(path, params=None):
    response = requests.get(f"{BASE_URL}{path}", params=params, timeout=(5, 15))
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise DataError("Expected a JSON object")
    return data


def _valid_character(value):
    return isinstance(value, dict) and isinstance(value.get("id"), int) and isinstance(value.get("name"), str) and bool(value["name"].strip())


def get_characters():
    characters = {}
    page = 1
    while True:
        data = _get("/characters", {"page": page, "limit": 100})
        items = data.get("items")
        if not isinstance(items, list):
            raise DataError("Missing character list")
        for character in items:
            if _valid_character(character):
                characters[character["id"]] = character
        total_pages = (data.get("meta") or {}).get("totalPages", 1)
        if not isinstance(total_pages, int) or not 1 <= total_pages <= 100:
            raise DataError("Invalid pagination")
        if page >= total_pages:
            break
        page += 1
    if not characters:
        raise DataError("Empty character list")
    return sorted(characters.values(), key=lambda item: item["name"].casefold())


def get_character(character_id):
    data = _get(f"/characters/{int(character_id)}")
    if not _valid_character(data):
        raise DataError("Invalid character detail")
    forms = data.get("transformations") or []
    if not isinstance(forms, list):
        raise DataError("Invalid transformations")
    data["transformations"] = [form for form in forms if isinstance(form, dict) and isinstance(form.get("name"), str)]
    # Correct the source label for Vegeta's existing final transformation.
    if data["id"] == 2:
        for form in data["transformations"]:
            if form.get("id") == 11:
                form["name"] = "Vegeta Ego"
    return data


def display_value(value):
    """Preserve source formatting, including zero, without interpreting Ki."""
    return "Unknown" if value is None or value == "" else str(value)


def image_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)
