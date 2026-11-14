"""The orthography edges take the NotationInfo test of lossless.

Clause 1: every output symbol is in the target inventory. Clause 2: the
reverse returns the input. A pass-through fails clause 1.

The Hiragana and Katakana inventories are the Unicode Script property:

    3041..3096    ; Hiragana # Lo  [86] HIRAGANA LETTER SMALL A..HIRAGANA LETTER SMALL KE
    309D..309E    ; Hiragana # Lm   [2] HIRAGANA ITERATION MARK..HIRAGANA VOICED ITERATION MARK
    309F          ; Hiragana # Lo       HIRAGANA DIGRAPH YORI
    1B001..1B11F  ; Hiragana # Lo [287] HIRAGANA LETTER ARCHAIC YE..HIRAGANA LETTER ARCHAIC WU
    1B123         ; Hiragana # Lo       HIRAGANA DIGRAPH KOTO
    1B132         ; Hiragana # Lo       HIRAGANA LETTER SMALL KO
    1B150..1B152  ; Hiragana # Lo   [3] HIRAGANA LETTER SMALL WI..HIRAGANA LETTER SMALL WO
    1F200         ; Hiragana # So       SQUARE HIRAGANA HOKA
    30A1..30FA    ; Katakana # Lo  [90] KATAKANA LETTER SMALL A..KATAKANA LETTER VO
    30FD..30FE    ; Katakana # Lm   [2] KATAKANA ITERATION MARK..KATAKANA VOICED ITERATION MARK
    30FF          ; Katakana # Lo       KATAKANA DIGRAPH KOTO
    31F0..31FF    ; Katakana # Lo  [16] KATAKANA LETTER SMALL KU..KATAKANA LETTER SMALL RO
    32D0..32FE    ; Katakana # So  [47] CIRCLED KATAKANA A..CIRCLED KATAKANA WO
    3300..3357    ; Katakana # So  [88] SQUARE APAATO..SQUARE WATTO
    FF66..FF6F    ; Katakana # Lo  [10] HALFWIDTH KATAKANA LETTER WO..HALFWIDTH KATAKANA LETTER SMALL TU
    FF71..FF9D    ; Katakana # Lo  [45] HALFWIDTH KATAKANA LETTER A..HALFWIDTH KATAKANA LETTER N
    1AFF0..1AFF3  ; Katakana # Lm   [4] KATAKANA LETTER MINNAN TONE-2..KATAKANA LETTER MINNAN TONE-5
    1AFF5..1AFFB  ; Katakana # Lm   [7] KATAKANA LETTER MINNAN TONE-7..KATAKANA LETTER MINNAN NASALIZED TONE-5
    1AFFD..1AFFE  ; Katakana # Lm   [2] KATAKANA LETTER MINNAN NASALIZED TONE-7..KATAKANA LETTER MINNAN NASALIZED TONE-8
    1B000         ; Katakana # Lo       KATAKANA LETTER ARCHAIC E
    1B120..1B122  ; Katakana # Lo   [3] KATAKANA LETTER ARCHAIC YI..KATAKANA LETTER ARCHAIC WU
    1B124..1B128  ; Katakana # Lo   [5] KATAKANA DIGRAPH TOKI..KATAKANA LETTER ALTERNATE WI
    1B155         ; Katakana # Lo       KATAKANA LETTER SMALL KO
    1B164..1B168  ; Katakana # Lo   [5] KATAKANA LETTER SMALL WI..KATAKANA LETTER SMALL ARCHAIC YE
    -- https://www.unicode.org/Public/UCD/latest/ucd/Scripts.txt (18.0.0)
"""
import pytest

from scriptconv import diacritics
from scriptconv.graph import DEFAULT_GRAPH, ConversionGraph
from scriptconv.translit import hira_to_kana, kana_to_hira


def code_points(*ranges):
    return {chr(c) for first, last in ranges for c in range(first, last + 1)}


HIRAGANA = code_points((0x3041, 0x3096), (0x309D, 0x309E), (0x309F, 0x309F),
                       (0x1B001, 0x1B11F), (0x1B123, 0x1B123), (0x1B132, 0x1B132),
                       (0x1B150, 0x1B152), (0x1F200, 0x1F200))
KATAKANA = code_points((0x30A1, 0x30FA), (0x30FD, 0x30FE), (0x30FF, 0x30FF),
                       (0x31F0, 0x31FF), (0x32D0, 0x32FE), (0x3300, 0x3357),
                       (0xFF66, 0xFF6F), (0xFF71, 0xFF9D), (0x1AFF0, 0x1AFF3),
                       (0x1AFF5, 0x1AFFB), (0x1AFFD, 0x1AFFE), (0x1B000, 0x1B000),
                       (0x1B120, 0x1B122), (0x1B124, 0x1B128), (0x1B155, 0x1B155),
                       (0x1B164, 0x1B168))


def edge(graph, src, dst):
    return next(e for e in graph._edges[src] if e.dst == dst)


def failures(forward, back, inventory, target):
    return sorted(c for c in inventory
                  if not set(forward(c)) <= target or back(forward(c)) != c)


def test_inventories_have_the_script_counts():
    assert (len(HIRAGANA), len(KATAKANA)) == (86 + 2 + 1 + 287 + 1 + 1 + 3 + 1,
                                              90 + 2 + 1 + 16 + 47 + 88 + 10 + 45
                                              + 4 + 7 + 2 + 1 + 3 + 5 + 1 + 5)


@pytest.mark.parametrize("src, dst, forward, back, inventory, target", [
    ("hira", "kana", hira_to_kana, kana_to_hira, HIRAGANA, KATAKANA),
    ("kana", "hira", kana_to_hira, hira_to_kana, KATAKANA, HIRAGANA),
])
def test_kana_edge_is_the_measured_round_trip(src, dst, forward, back, inventory, target):
    assert edge(DEFAULT_GRAPH, src, dst).lossless is (not failures(forward, back, inventory, target))


@pytest.mark.parametrize("forward, kana", [
    (hira_to_kana, "ゟ"),   # HIRAGANA DIGRAPH YORI; KATAKANA DIGRAPH KOTO is another word
    (kana_to_hira, "ヷ"),   # KATAKANA LETTER VA has no hiragana letter
    (kana_to_hira, "ㇰ"),   # KATAKANA LETTER SMALL KU
])
def test_kana_with_no_counterpart_passes_through(forward, kana):
    assert forward(kana) == kana


def test_common_kana_still_round_trip():
    assert kana_to_hira(hira_to_kana("こんにちは")) == "こんにちは"
    assert hira_to_kana("こんにちは") == "コンニチハ"


# A letter with an overlay mark and the bare letter strip to one string, so no
# reverse returns both: clause 2 fails for every mark.
@pytest.mark.parametrize("lang, base, marks", [
    ("ru", "а", diacritics._STRESS_MARKS),
    ("ar", "ب", diacritics._ARABIC_MARKS),
    ("he", "ב", diacritics._HEBREW_MARKS),
])
def test_strip_maps_every_mark_onto_the_bare_letter(lang, base, marks):
    assert {diacritics.strip_diacritics(base + chr(m), lang) for m in marks} == {base}


def test_strip_edge_is_not_lossless():
    graph = ConversionGraph().extend(diacritics.register)
    assert edge(graph, diacritics.DIACRITIZED, "text").lossless is False
