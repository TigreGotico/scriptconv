"""Cuneiform signs against the Unicode names for them.

The table is not shipped — it is read out of `unicodedata` — so these tests
are as much about the reading being right as about the conversion being right.
"""

import unicodedata

import pytest

from scriptconv import DEFAULT_GRAPH, char_script, detect_script
from scriptconv.cuneiform import (CUNEIFORM_BLOCKS, cuneiform_to_sign_names,
                                  is_cuneiform, sign_for_name, sign_name,
                                  sign_names_to_cuneiform)
from scriptconv.notation import UnknownSymbolError


# --- the signs themselves --------------------------------------------------

_GOLD = [
    ("\U00012000", "A"),
    ("\U0001202D", "AN"),
    ("\U00012217", "LUGAL"),
    ("\U0001208D", "E2"),
    ("\U00012001", "A TIMES A"),
]


@pytest.mark.parametrize("sign,name", _GOLD)
def test_sign_name_gold(sign, name):
    assert sign_name(sign) == name
    assert sign_for_name(name) == sign


@pytest.mark.parametrize("sign,name", _GOLD)
def test_the_name_is_the_one_unicode_gives(sign, name):
    """Gold above is hand-written; this checks it against the standard
    rather than against the same table it came from."""
    assert unicodedata.name(sign).endswith(name)


def test_every_named_sign_in_the_blocks_converts_both_ways():
    """The round trip, over every sign this interpreter's Unicode knows."""
    for start, end in CUNEIFORM_BLOCKS:
        for codepoint in range(start, end + 1):
            sign = chr(codepoint)
            name = sign_name(sign)
            if name is None:
                continue
            assert sign_for_name(name) == sign, f"{sign!r} ({name}) lost"


def test_names_are_unique_so_nothing_is_shadowed():
    """Two signs sharing a name would make the reverse map silently pick
    one of them."""
    names = [sign_name(chr(cp))
             for start, end in CUNEIFORM_BLOCKS
             for cp in range(start, end + 1)
             if sign_name(chr(cp)) is not None]
    assert len(names) == len(set(names))


# --- strings ---------------------------------------------------------------

def test_a_sign_sequence_round_trips():
    signs = "\U0001202D\U00012217\U0001208D"
    assert sign_names_to_cuneiform(cuneiform_to_sign_names(signs)) == signs


def test_a_compound_name_is_read_whole_not_as_its_first_word():
    """`A TIMES A` must not be read as `A` followed by unmatched text."""
    assert sign_names_to_cuneiform("A TIMES A") == "\U00012001"


def test_matching_is_case_insensitive():
    assert sign_names_to_cuneiform("an lugal") == \
        sign_names_to_cuneiform("AN LUGAL")


def test_input_whitespace_is_not_carried():
    """Stated rather than assumed: the two directions cannot agree on what a
    space meant, because names need separating and signs do not."""
    assert cuneiform_to_sign_names("\U0001202D \U00012217") == "AN LUGAL"
    assert sign_names_to_cuneiform("AN LUGAL") == "\U0001202D\U00012217"


# --- the errors policy, as everywhere else in the library ------------------

def test_unknown_input_follows_the_errors_policy():
    assert cuneiform_to_sign_names("x", errors="pass") == "x"
    assert cuneiform_to_sign_names("x", errors="ignore") == ""
    assert cuneiform_to_sign_names("x", errors="replace") == "?"
    with pytest.raises(UnknownSymbolError):
        cuneiform_to_sign_names("x", errors="strict")


def test_a_name_unicode_never_assigned_follows_the_errors_policy():
    with pytest.raises(UnknownSymbolError):
        sign_names_to_cuneiform("NOTASIGN", errors="strict")


# --- identity --------------------------------------------------------------

def test_cuneiform_is_detected_as_its_own_script():
    assert char_script("\U0001202D") == "Xsux"
    assert detect_script("\U0001202D\U00012217") == "Xsux"


def test_is_cuneiform_agrees_with_the_table():
    assert is_cuneiform("\U0001202D")
    assert not is_cuneiform("a")


# --- the graph -------------------------------------------------------------

def test_the_graph_routes_both_directions():
    assert DEFAULT_GRAPH.can_convert("cuneiform", "sign-names")
    assert DEFAULT_GRAPH.can_convert("sign-names", "cuneiform")
    assert DEFAULT_GRAPH.convert("\U0001202D", "cuneiform", "sign-names") == "AN"


# --- readings, from the optional cuneiscribe table -------------------------

def _has_cuneiscribe():
    import importlib.util
    spec = importlib.util.find_spec("cuneiscribe")
    return spec is not None and bool(spec.submodule_search_locations)


requires_cuneiscribe = pytest.mark.skipif(
    not _has_cuneiscribe(), reason="needs scriptconv[cuneiscribe]")


def test_a_missing_reading_list_names_the_extra():
    """The convention every optional backend here follows: explain, do not
    fail obscurely. Runs whether or not the package is installed."""
    import importlib.util

    from scriptconv import cuneiform as module

    real, module._READINGS = module._READINGS, None
    find_spec = importlib.util.find_spec
    importlib.util.find_spec = lambda name, *a, **k: (
        None if name == "cuneiscribe" else find_spec(name, *a, **k))
    try:
        with pytest.raises(ImportError) as err:
            module.readings_to_cuneiform("a-na")
        assert "cuneiscribe" in str(err.value)
    finally:
        importlib.util.find_spec = find_spec
        module._READINGS = real


@requires_cuneiscribe
def test_reading_the_table_does_not_import_torch():
    """The package is installed for its data file. Importing it would pull
    torch and transformers in to read a JSON file."""
    import subprocess
    import sys

    code = (
        "import sys;"
        "from scriptconv.cuneiform import sign_readings_table as t;"
        "t();"
        "print('torch' in sys.modules or 'transformers' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True)
    assert out.stdout.strip() == "False", out.stdout + out.stderr


@requires_cuneiscribe
@pytest.mark.parametrize("reading,signs", [
    ("a-na", "\U00012000\U0001223E"),
    ("dan-nu", "\U00012197\U00012261"),
    ("LUGAL", "\U00012217"),
])
def test_readings_convert_to_signs(reading, signs):
    from scriptconv import readings_to_cuneiform
    assert readings_to_cuneiform(reading) == signs


@requires_cuneiscribe
def test_determinatives_are_dropped():
    """`{d}` before a divine name is a silent classifier with no sign."""
    from scriptconv import readings_to_cuneiform
    assert readings_to_cuneiform("{d}en-lil2") == readings_to_cuneiform("en-lil2")


@requires_cuneiscribe
def test_words_keep_their_boundaries_and_signs_do_not():
    from scriptconv import readings_to_cuneiform
    assert " " in readings_to_cuneiform("a-na KUR")
    assert " " not in readings_to_cuneiform("a-na")


@requires_cuneiscribe
def test_an_index_digit_is_part_of_the_reading_not_decoration():
    """cuneiscribe's own lookup falls back to stripping subscripts, so an
    unknown `u₂` silently becomes the sign for `u` — a different sign. An
    unknown reading has to reach the errors policy instead."""
    from scriptconv import readings_to_cuneiform
    with pytest.raises(UnknownSymbolError):
        readings_to_cuneiform("zzz9", errors="strict")


@requires_cuneiscribe
def test_an_unknown_reading_follows_the_errors_policy():
    from scriptconv import readings_to_cuneiform
    assert readings_to_cuneiform("zzz", errors="pass") == "zzz"
    assert readings_to_cuneiform("zzz", errors="ignore") == ""
    assert readings_to_cuneiform("zzz", errors="replace") == "?"


@requires_cuneiscribe
def test_the_graph_routes_readings_to_signs():
    from scriptconv import DEFAULT_GRAPH
    assert DEFAULT_GRAPH.convert("a-na", "sign-readings", "cuneiform") == \
        "\U00012000\U0001223E"
