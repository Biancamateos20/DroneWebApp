import re
import unicodedata


COLOR_NAME_BY_ALIAS = {
    "#1E90FF": "AZUL",
    "#FF0000": "ROJO",
    "#32CD32": "VERDE",
    "#FFD700": "AMARILLO",
    "#800080": "MORADO",
    "#FF1493": "ROSA",
    "#00CED1": "TURQUESA",
    "#FF8C00": "NARANJA"
}


COLOR_SYNONYMS = {
    "AZUL": ["azul", "azules"],
    "ROJO": ["rojo", "rojos"],
    "VERDE": ["verde", "verdes"],
    "AMARILLO": ["amarillo", "amarillos"],
    "MORADO": ["morado", "morados", "morao", "violeta", "purpura", "lila"],
    "ROSA": ["rosa", "rosas", "fucsia", "fuscia", "pink"],
    "TURQUESA": ["turquesa", "cian", "cyan", "celeste"],
    "NARANJA": ["naranja", "naranjas", "anaranjado", "anaranjada"]
}


def normalize_voice_text(text):
    if not isinstance(text, str):
        return ""

    normalized = unicodedata.normalize("NFD", text.strip().lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = re.sub(r"[^a-z0-9# ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def get_color_name_from_alias(alias):
    normalized_alias = str(alias or "").strip().upper()
    return COLOR_NAME_BY_ALIAS.get(normalized_alias)


def resolve_spoken_color(text, allowed_aliases):
    normalized_text = normalize_voice_text(text)
    if not normalized_text:
        return None

    allowed = []
    for alias in allowed_aliases or []:
        normalized_alias = str(alias or "").strip().upper()
        color_name = get_color_name_from_alias(normalized_alias)
        if not normalized_alias or not color_name:
            continue
        allowed.append((normalized_alias, color_name))

    for alias, color_name in allowed:
        if normalized_text == normalize_voice_text(color_name):
            return alias

    for alias, color_name in allowed:
        synonyms = COLOR_SYNONYMS.get(color_name, [])
        for synonym in synonyms:
            if normalize_voice_text(synonym) == normalized_text:
                return alias

    words = normalized_text.split(" ")
    for alias, color_name in allowed:
        synonyms = [color_name] + COLOR_SYNONYMS.get(color_name, [])
        normalized_synonyms = {normalize_voice_text(value) for value in synonyms}
        for word in words:
            if word in normalized_synonyms:
                return alias

    return None
