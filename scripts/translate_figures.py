"""
Traduit les figures du billet en anglais, sans rien recalculer.

Les SVG sont produits par `publication/figures.py` à partir des simulations ;
les régénérer dans une autre langue supposerait de refaire tourner le modèle. Ce
script part donc des SVG déjà écrits et n'en traduit que le texte : les tracés,
les échelles et les couleurs sont copiés à l'identique. Une exécution prend
quelques secondes au lieu de plusieurs minutes de Monte-Carlo.

Deux sources de texte dans un SVG Vega :

- les `<text>` (et leurs `<tspan>`), c'est-à-dire ce qui est visible ;
- les `aria-label`, dont Vega écrit un exemplaire PAR POINT de données, sous la
  forme `Champ: valeur; Champ: valeur`. Seuls les NOMS DE CHAMPS y sont en
  français : on applique donc le même dictionnaire aux noms, jamais aux valeurs.
  Sans cela il faudrait traduire des milliers de chaînes au lieu de quelques
  centaines.

Toute chaîne française rencontrée sans traduction fait ÉCHOUER le script. C'est
délibéré : un libellé renommé dans un générateur doit casser la traduction au
lieu de laisser passer silencieusement du français dans la version anglaise.

Usage :
    python scripts/translate_figures.py            # écrit site/public/figures/en/
    python scripts/translate_figures.py --check    # signale les manques sans écrire
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from analyse_legislatives.config import PROJECT_ROOT

FIGURES_DIR = PROJECT_ROOT / "site/public/figures"
OUTPUT_DIR = FIGURES_DIR / "en"
TRANSLATIONS_PATH = PROJECT_ROOT / "config/figure-translations.json"

PARTY_CODES = {
    "NFP+",
    "RN+",
    "ENS+",
    "LR",
    "DVD",
    "DVG",
    "DIV",
    "NON_EXPRIMES",
    "NE",
    "ENS",
    "RN",
    "UG",
    "EXG",
    "DSV",
    "UXD",
    "REC",
    "HOR",
    "UDI",
    "MDM",
    "DVC",
}
"""Sigles du ministère : ils sont identiques dans les deux langues."""

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
"""Champ interne de Vega (`model_label`, `p05`, `x0`…) : jamais affiché."""


def _french_number(match: re.Match) -> str:
    """`26 348` -> `26,348` et `0,5` -> `0.5`."""
    digits = match.group(0)
    if "," in digits:
        whole, _, frac = digits.partition(",")
        return f"{_french_number_group(whole)}.{frac}"
    return _french_number_group(digits)


def _french_number_group(digits: str) -> str:
    plain = re.sub(r"[\s  ]", "", digits)
    return f"{int(plain):,}" if plain.isdigit() and len(plain) > 3 else plain


NUMBER = re.compile(r"\d[\d\s  ]*(?:,\d+)?")


def localise_numbers(text: str) -> str:
    """Applique les conventions anglaises aux nombres (virgule décimale, espaces)."""
    return NUMBER.sub(_french_number, text)


PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^([\d\s  ]+) voix$"), r"\1 votes"),
    (re.compile(r"^solde net : (-?[\d\s  ]+) voix$"), r"net balance: \1 votes"),
    (re.compile(r"^([\d,\s]+) % des inscrits$"), r"\1% of registered"),
    (re.compile(r"^démobilisation(\s+)([\d,]+) %$"), r"demobilisation\1\2%"),
    (re.compile(r"^mobilisation(\s+)([\d,]+) %$"), r"mobilisation\1\2%"),
    (
        re.compile(r"^reports vers les non-exprimés(\s+)([\d,]+) %$"),
        r"transfers to non-expressed\1\2%",
    ),
    (
        re.compile(r"^décale et élargit(\s+)·(\s+)([\d,]+) bit$"),
        r"shifts and widens\1·\2\3 bit",
    ),
    (re.compile(r"^décale(\s+)·(\s+)([\d,]+) bit$"), r"shifts\1·\2\3 bit"),
    (re.compile(r"^élargit(\s+)·(\s+)([\d,]+) bit$"), r"widens\1·\2\3 bit"),
    (
        re.compile(r"^sans effet net(\s+)·(\s+)([\d,]+) bit$"),
        r"no net effect\1·\2\3 bit",
    ),
    (re.compile(r"^décile le plus bas$"), "lowest decile"),
    (re.compile(r"^décile le plus haut$"), "highest decile"),
    (re.compile(r"^→ (.+)$"), r"→ \1"),
    (re.compile(r"^(\S+) → (\S+)$"), r"\1 → \2"),
]
"""Chaînes qui ne diffèrent que par un nombre : une règle vaut mieux qu'une
entrée de dictionnaire par valeur, sinon le dictionnaire se périme dès qu'un
chiffre bouge."""


FRENCH = re.compile(
    r"[éèêëàâäçùûüôöîïœÉÈÊÀÂÇÔÎ]"
    r"|\b(le|la|les|des|du|une|un|aux|au|dans|pour|avec|selon|entre|par|sur"
    r"|et|ou|est|sont|chaque|même|autre|vers|sans|leur|plus|moins)\b",
    re.IGNORECASE,
)
"""Ce qui doit faire échouer le script, c'est du FRANÇAIS non traduit — pas
toute chaîne absente du dictionnaire. Vega produit lui-même quantité de libellés
anglais (`X-axis for a linear scale…`, `score: 15.7`) qu'il serait absurde de
recenser, et les traductions déjà appliquées ne doivent pas être re-signalées."""


VEGA_TEMPLATE = re.compile(
    r"^(?:Subtitle text|Title text|[XY]-axis|Symbol legend|Gradient legend|Legend)\b"
)
"""Gabarits d'accessibilité de Vega. Ils contiennent « : » et « ; » comme les
étiquettes de données, mais leur texte français est entre apostrophes : les
découper en paires « Champ: valeur » les met en pièces."""


class MissingTranslation(Exception):
    pass


NARROW_SPACES = dict.fromkeys(map(ord, "\u202f\u00a0\u2009"), " ")


def normalise(text: str) -> str:
    """Ramène les espaces typographiques à l'espace ordinaire.

    Les SVG séparent les milliers par une espace fine insécable ; sans cette
    normalisation, `23 819` dans le dictionnaire ne rejoindrait jamais
    `23\u202f819` dans la figure, et chaque libellé chiffré serait déclaré manquant.
    """
    return text.translate(NARROW_SPACES)


class Translator:
    def __init__(self, table: dict[str, str]):
        self.table = {normalise(k): v for k, v in table.items()}
        self.missing: set[str] = set()
        self.used: set[str] = set()

    def needs_translation(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped or stripped in PARTY_CODES or IDENTIFIER.fullmatch(stripped):
            return False
        # Purement numérique / symbolique : traité par `localise_numbers`.
        return not re.fullmatch(r"[-+−–—\s0-9.,%()\[\]/:α-ωΑ-Ω=&#;]*", stripped)

    def __call__(self, text: str) -> str:
        stripped = normalise(text).strip()
        if not self.needs_translation(text):
            return localise_numbers(text)
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        if stripped in self.table:
            self.used.add(stripped)
            return lead + self.table[stripped] + trail
        for pattern, replacement in PATTERNS:
            if pattern.fullmatch(stripped):
                translated = localise_numbers(pattern.sub(replacement, stripped))
                return lead + translated + trail
        if FRENCH.search(stripped):
            self.missing.add(stripped)
        return text

    ENTITY = re.compile(r"&#?\w{1,8};")

    def _protect(self, label: str) -> tuple[str, list[str]]:
        """Met les entités HTML à l'abri du découpage.

        Le séparateur des étiquettes Vega est « ; », qui termine aussi toute
        entité (`&#xA;`, `&#961;`). Sans cette mise à l'abri, `Médiane et&#xA;`
        est coupé en deux et l'entité détruite.
        """
        kept: list[str] = []

        def stash(match: re.Match) -> str:
            kept.append(match.group(0))
            return f"\x00{len(kept) - 1}\x00"

        return self.ENTITY.sub(stash, label), kept

    @staticmethod
    def _restore(text: str, kept: list[str]) -> str:
        return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)

    def aria(self, label: str) -> str:
        """Traduit un `aria-label`.

        Vega en produit plusieurs formes, et une seule chaîne peut en combiner
        deux (un titre d'axe ET une liste de valeurs). Les gabarits sont donc
        appliqués l'un APRÈS l'autre, jamais en alternative — sinon le premier
        qui correspond masque les suivants.

        Les illustrations écrites à la main portent, elles, une simple phrase :
        si aucun gabarit ne s'applique, la chaîne entière passe par le
        dictionnaire. Sans ce repli, ces phrases traversaient le script sans être
        traduites ni signalées comme manquantes.
        """
        label, entities = self._protect(label)
        pairs = label.split(";")
        # Étiquette de données Vega : « Champ: valeur; Champ: valeur ». Les
        # paires peuvent s'imbriquer (« NFP+ : de: 150 »), donc on traduit chaque
        # segment séparément plutôt que d'exiger un format global — une seule
        # paire mal formée ne doit pas faire retomber toute la chaîne dans le
        # chemin des gabarits, qui la mettrait en pièces.
        if not VEGA_TEMPLATE.match(label) and ":" in label:
            # Chaque segment est restauré AVANT traduction : le dictionnaire est
            # écrit avec les entités telles qu'elles figurent dans le SVG.
            return ";".join(
                ":".join(
                    self(self._restore(segment, entities))
                    for segment in pair.split(":")
                )
                for pair in pairs
            )

        translated = label
        translated = re.sub(
            r"((?:titled|text) ')(.*?)('(?= for | with |\s*$))",
            lambda m: m.group(1) + self(m.group(2)) + m.group(3),
            translated,
        )
        translated = re.sub(
            r"((?:starting|ending) with )([^,]+?)(?=( and ending with | *$))",
            lambda m: m.group(1) + self(m.group(2)),
            translated,
        )
        values = re.match(r"(.*\bvalues: )(.+)$", translated)
        if values:
            translated = values.group(1) + ", ".join(
                self(v) for v in values.group(2).split(", ")
            )
        if translated == label:
            return self(self._restore(label, entities))
        return self._restore(translated, entities)


def translate_svg(source: str, translate: Translator) -> str:
    def text_node(match: re.Match) -> str:
        if match.group(1) is None:  # balise auto-fermante : rien à traduire
            return match.group(0)
        body = match.group(2)
        if "<tspan" in body:
            body = re.sub(
                r"(<tspan[^>]*>)([^<]*)(</tspan>)",
                lambda m: m.group(1) + translate(m.group(2)) + m.group(3),
                body,
            )
            # Texte hors <tspan>, entre ou autour des balises.
            body = re.sub(
                r"(^|>)([^<>]+)(<|$)",
                lambda m: m.group(1) + translate(m.group(2)) + m.group(3),
                body,
            )
        else:
            body = translate(body)
        return match.group(1) + body + match.group(3)

    # L'alternance traite d'abord `<text …/>` : sans elle, une balise
    # auto-fermante serait avalée par le `.*?` et du balisage brut finirait
    # traité comme du texte à traduire.
    out = re.sub(
        r"<text[^>]*/>|(<text[^>]*>)(.*?)(</text>)", text_node, source, flags=re.S
    )
    return re.sub(
        r'aria-label="([^"]*)"',
        lambda m: 'aria-label="' + translate.aria(m.group(1)) + '"',
        out,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="signale les manques sans écrire"
    )
    args = parser.parse_args()

    table = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    translate = Translator(table)

    sources = sorted(p for p in FIGURES_DIR.glob("*.svg"))
    rendered: dict[Path, str] = {}
    for path in sources:
        rendered[path] = translate_svg(path.read_text(encoding="utf-8"), translate)

    if translate.missing:
        print(
            f"{len(translate.missing)} chaînes sans traduction "
            f"(à ajouter dans {TRANSLATIONS_PATH.relative_to(PROJECT_ROOT)}) :",
            file=sys.stderr,
        )
        for text in sorted(translate.missing):
            print(f"  {text!r}", file=sys.stderr)
        raise MissingTranslation(f"{len(translate.missing)} chaînes non traduites")

    unused = set(table) - translate.used
    if unused:
        print(f"note : {len(unused)} entrées du dictionnaire ne servent plus")

    if args.check:
        print(f"OK — {len(sources)} figures traduisibles, aucune chaîne manquante")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in rendered.items():
        (OUTPUT_DIR / path.name).write_text(content, encoding="utf-8")
    # Les GIF et PNG n'ont pas de texte : ils sont partagés tels quels.
    for path in sorted(FIGURES_DIR.glob("*.gif")) + sorted(FIGURES_DIR.glob("*.png")):
        shutil.copy2(path, OUTPUT_DIR / path.name)
    print(
        f"{len(rendered)} figures écrites dans {OUTPUT_DIR.relative_to(PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()
