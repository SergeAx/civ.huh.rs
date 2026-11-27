"""Serbia's administrative okruzi (Uredba o upravnim okruzima), with Grad Beograd as "00".

`abbr` is the vehicle-registration code of the okrug's seat: short, unique and familiar to anyone in Serbia, so
it serves as the map's short label and as the okrug's key in URLs.
"""

from __future__ import annotations

_TABLE = [
    ("00", "BG", "Град Београд", "Beograd"),
    ("01", "SU", "Севернобачки", "Subotica"),
    ("02", "ZR", "Средњобанатски", "Zrenjanin"),
    ("03", "KI", "Севернобанатски", "Kikinda"),
    ("04", "PA", "Јужнобанатски", "Pančevo"),
    ("05", "SO", "Западнобачки", "Sombor"),
    ("06", "NS", "Јужнобачки", "Novi Sad"),
    ("07", "SM", "Сремски", "Sremska Mitrovica"),
    ("08", "ŠA", "Мачвански", "Šabac"),
    ("09", "VA", "Колубарски", "Valjevo"),
    ("10", "SD", "Подунавски", "Smederevo"),
    ("11", "PO", "Браничевски", "Požarevac"),
    ("12", "KG", "Шумадијски", "Kragujevac"),
    ("13", "JA", "Поморавски", "Jagodina"),
    ("14", "BO", "Борски", "Bor"),
    ("15", "ZA", "Зајечарски", "Zaječar"),
    ("16", "UE", "Златиборски", "Užice"),
    ("17", "ČA", "Моравички", "Čačak"),
    ("18", "KV", "Рашки", "Kraljevo"),
    ("19", "KŠ", "Расински", "Kruševac"),
    ("20", "NI", "Нишавски", "Niš"),
    ("21", "PK", "Топлички", "Prokuplje"),
    ("22", "PI", "Пиротски", "Pirot"),
    ("23", "LE", "Јабланички", "Leskovac"),
    ("24", "VR", "Пчињски", "Vranje"),
    ("25", "PR", "Косовски", "Priština"),
    ("26", "PE", "Пећки", "Peć"),
    ("27", "PZ", "Призренски", "Prizren"),
    ("28", "KM", "Косовскомитровачки", "Kosovska Mitrovica"),
    ("29", "GL", "Косовскопоморавски", "Gnjilane"),
]

_LAT = str.maketrans({
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J",
    "К": "K", "Л": "L", "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Џ": "Dž", "Ш": "Š",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i", "ј": "j",
    "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "ћ": "ć", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "č", "џ": "dž", "ш": "š",
})


def to_latin(s: str) -> str:
    """Serbian Cyrillic → Latin (mixed-case digraphs: Љубовија → Ljubovija)."""
    return s.translate(_LAT)


KIM_OKRUZI = {"25", "26", "27", "28", "29"}

OKRUZI = [
    {"code": code, "abbr": abbr, "name_cyr": name, "name_lat": to_latin(name), "seat_lat": seat, "kim": code in KIM_OKRUZI}
    for code, abbr, name, seat in _TABLE
]
