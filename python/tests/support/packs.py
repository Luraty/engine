"""Small but genuine language packs, ported from src/testing/packs.ts."""

import luraty_engine as L


def _build(config, data):
    result = L.create_pack(config, data)
    if result.ok:
        return result.value
    message = f'bad test fixture pack "{config["id"]}": {result.error.message}'

    def boom(*_):
        raise RuntimeError(message)

    return L.LanguagePack(id=config["id"], split=boom, key=boom, candidates=boom, rank=boom, compare=boom)


FRENCH_CONFIG = {
    "id": "fr",
    "tokenize": {"strategy": "regex", "pattern": "[a-zA-Zà-öø-ÿ']+"},
    "normalize": ["lowercase", "stripPunctuation", "foldLatinDiacritics"],
    "affixes": {"prefixes": ["l'", "d'", "j'", "n'", "qu'", "s'", "c'", "m'", "t'"], "onlyIfRemainderKnown": True},
    "compare": ["lowercase", "stripPunctuation", "foldLatinDiacritics"],
}

FRENCH_DATA = {
    "frequency": (
        "de la le et les des en un une du que est il pour dans qui ne sur se pas plus par je avec tout "
        "faire son mettre autre on mais nous comme ou si leur y dire elle avant deux mots automne "
        "marche marché pain vendre acheter maison eau"
    ),
    "lemmas": {
        "vais": "aller",
        "vas": "aller",
        "va": "aller",
        "allons": "aller",
        "allez": "aller",
        "vont": "aller",
        "suis": "etre",
        "es": "etre",
        "est": "etre",
        "sommes": "etre",
    },
}

ARABIC_CONFIG = {
    "id": "ar-msa",
    "tokenize": {"strategy": "regex", "pattern": "[\\u0600-\\u06FF]+"},
    "normalize": ["stripArabicDiacritics", "stripTatweel", "normalizeArabicAlef", "normalizeArabicFinals"],
    "affixes": {"prefixes": ["ال", "لل", "و", "ب", "ل", "ف", "ك"], "onlyIfRemainderKnown": True},
    "compare": [
        "stripPunctuation",
        "stripArabicDiacritics",
        "stripTatweel",
        "normalizeArabicAlef",
        "normalizeArabicFinals",
    ],
}

ARABIC_DATA = {
    "frequency": (
        "في من على أن إلى عن مع هذا التي كان قد لا ما هو كل بعد بين حول عند سوق كتاب مدرسة بيت ماء خبز "
        "شارع مطار طبيب قطار جريدة حكومة ولد وقت مدينة كتب مدرس"
    ),
    "lemmas": {"كتب": ["كتب", "كتاب"], "مدرسة": ["مدرسة", "مدرس"]},
}

GERMAN_CONFIG = {
    "id": "de",
    "tokenize": {"strategy": "regex", "pattern": "[a-zA-ZäöüÄÖÜßẞ]+"},
    "normalize": ["lowercase", "stripPunctuation", "foldGermanUmlauts", "foldLatinDiacritics"],
    "affixes": {"prefixes": ["ge"], "onlyIfRemainderKnown": True},
    "compare": ["lowercase", "stripPunctuation", "foldGermanUmlauts", "foldLatinDiacritics"],
}

GERMAN_DATA = {
    "frequency": (
        "der die und in den von zu das mit sich des auf fuer ist im dem nicht ein eine als auch es an "
        "werden aus er hat dass sie nach wird bei einer um am sind noch wie einem ueber einen so zum "
        "war haben nur oder aber vor zur bis mehr durch man sein wurde sei ich wir ihr mich mir dich "
        "dir uns euch kein sehr schon immer wenn dann weil dass hier dort heute morgen gestern jahr "
        "tag zeit mensch kind frau mann haus stadt land wasser brot markt strasse bahnhof arzt zeitung "
        "regierung schule buch tuer fenster garten baum blume himmel sonne mond stern gehen kommen "
        "machen sagen sehen geben nehmen finden denken wissen kennen lesen schreiben sprechen hoeren "
        "essen trinken kaufen verkaufen wohnen arbeiten lernen spielen laufen fahren schoen gross "
        "klein alt neu jung gut schlecht warm kalt schnell langsam"
    ),
    "lemmas": {
        "bin": "sein",
        "bist": "sein",
        "ist": "sein",
        "sind": "sein",
        "seid": "sein",
        "war": "sein",
        "waren": "sein",
        "gewesen": "sein",
        "habe": "haben",
        "hast": "haben",
        "hat": "haben",
        "habt": "haben",
        "hatte": "haben",
        "hatten": "haben",
        "gehe": "gehen",
        "gehst": "gehen",
        "geht": "gehen",
        "ging": "gehen",
        "gegangen": "gehen",
        "kaufe": "kaufen",
        "kaufst": "kaufen",
        "kauft": "kaufen",
        "gekauft": "kaufen",
        "lese": "lesen",
        "liest": "lesen",
        "las": "lesen",
        "gelesen": "lesen",
        "trinke": "trinken",
        "trinkt": "trinken",
        "getrunken": "trinken",
        "zählt": "zählen",
        "zahlt": "zahlen",
        "läuft": "laufen",
        "fährt": "fahren",
        "trägt": "tragen",
    },
}

french_pack = _build(FRENCH_CONFIG, FRENCH_DATA)
arabic_pack = _build(ARABIC_CONFIG, ARABIC_DATA)
german_pack = _build(GERMAN_CONFIG, GERMAN_DATA)
