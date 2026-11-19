"""Tests for the sentence gate, scriptconv.testing.compare.

Every expected PER below is an edit distance counted by hand on the strings in
the test, never a value read back from the harness.
"""
import pytest

from scriptconv.testing import compare as gate
from scriptconv.testing.compare import (
    COLUMNS, Row, edit_distance, main, per_by_category, read_tsv, segments,
    stage_gain, verdict,
)

PLAIN = "pa ta"      # 4 segments, every backend reads it right
HOMOGRAPH = "so lo"  # 4 segments; the backend reads "su lo" until its homograph stage runs


def _fix_homograph(ipa):
    return ipa.replace("su", "so")


def _drop_last_word(ipa):
    return ipa.rsplit(" ", 1)[0]


def _noop(ipa):
    return ipa


# The sentence that each text made by _rows spells.
SPELLED = {}


class Table:
    """A backend that reads a text through a fixed table, then runs its stages in order.
    A text made by _rows reads as the sentence it spells."""

    def __init__(self, table, stages=None):
        self.table = table
        self.stages = dict(stages or {})

    def phonemize(self, text, lang):
        sentence = SPELLED.get(text, text)
        ipa = self.table.get(sentence, sentence)
        for stage in self.stages.values():
            ipa = stage(ipa)
        return [list(ipa)]


class AblatableTable(Table):
    def without(self, stage):
        if stage not in self.stages:
            raise ValueError(f"no stage {stage!r}")
        return AblatableTable(self.table, {k: v for k, v in self.stages.items() if k != stage})


BASE = {HOMOGRAPH: "su lo"}
O2I = Table(BASE)


def make_good_backend():
    return AblatableTable(BASE, {"homographs": _fix_homograph})


def make_rigid_backend():
    return Table(BASE, {"homographs": _fix_homograph})


def _rows(spec, tier="gold"):
    """Rows from (category, sentence, expected_ipa, count) tuples. A sentence set
    never repeats a text, so each row has a text of its own that spells *sentence*."""
    rows = []
    for category, sentence, expected, count in spec:
        for _ in range(count):
            text = "frase" + "".join("abcdefghij"[int(d)] for d in str(len(SPELLED)))
            SPELLED[text] = sentence
            rows.append(Row(f"{tier}{len(rows)}", "pt-PT", category, text, expected, "test", tier))
    return rows


GOLD = _rows([("plain", PLAIN, PLAIN, 5), ("homograph", HOMOGRAPH, HOMOGRAPH, 5)])


# --- PER against hand-computed edit distances ---

@pytest.mark.parametrize("ref, hyp, distance", [
    ("kat", "kat", 0),
    ("kat", "bat", 1),          # one substitution
    ("kat", "kats", 1),         # one insertion
    ("kats", "kat", 1),         # one deletion
    ("", "ab", 2),
    ("ab", "", 2),
    ("kitten", "sitting", 3),   # k->s, e->i, +g
    ("ab", "ba", 2),            # a swap costs two edits
])
def test_edit_distance_matches_hand_count(ref, hyp, distance):
    assert edit_distance(list(ref), list(hyp)) == distance


@pytest.mark.parametrize("ipa, expected", [
    ("ˈkaʃ.tɐ", ["ˈ", "k", "a", "ʃ", "t", "ɐ"]),  # stress is a segment, a syllable mark is not
    ("ˌpaˈta", ["ˌ", "p", "a", "ˈ", "t", "a"]),
    ("aː b‿c", ["aː", "b", "c"]),                  # length stays on its vowel; spaces and links go
    ("mɐ̃w̃", ["m", "ɐ̃", "w̃"]),               # a combining mark stays on its base
    ("a | b ‖ c", ["a", "b", "c"]),
    ("ka\u0303w", ["k", "\u00e3", "w"]),          # a decomposed vowel equals its composed form
    ("aˌpa", ["a", "ˌ", "p", "a"]),                # secondary stress inside a word
    ("t\u0361sa", ["t", "s", "a"]),                # a tie bar above is not a segment
    ("t\u035csa", ["t", "s", "a"]),                # nor is a tie bar below
])
def test_segments_match_hand_split(ipa, expected):
    assert segments(ipa) == expected


def test_per_by_category_matches_hand_count():
    rows = [
        Row("1", "pt-PT", "plain", "x1", "ab", "t", "gold"),
        Row("2", "pt-PT", "plain", "x2", "abcd", "t", "gold"),
        Row("3", "pt-PT", "homograph", "x3", "kasa", "t", "gold"),
    ]
    backend = Table({"x1": "ab", "x2": "abd", "x3": "kaza"})
    # plain: 0 edits on 2 segments + 1 deletion on 4 segments = 1/6
    # homograph: 1 substitution on 4 segments = 1/4
    assert per_by_category(rows, backend) == {"plain": 1 / 6, "homograph": 1 / 4}


def test_per_reads_every_sentence():
    class TwoSentences:
        def phonemize(self, text, lang):
            return [list("ab"), list("cd")]

    rows = [Row("1", "pt-PT", "plain", "x", "ab cd", "t", "gold")]
    assert per_by_category(rows, TwoSentences()) == {"plain": 0.0}


def test_tie_bars_score_as_the_bare_sequence():
    rows = [Row("1", "pt-PT", "plain", "x1", "ˈt\u0361sa t\u035cʃu", "t", "gold")]
    # the backend writes both affricates with no tie bar: 0 edits on 7 segments
    assert per_by_category(rows, Table({"x1": "ˈtsa tʃu"})) == {"plain": 0.0}


def test_reference_with_no_segments_is_skipped_with_a_warning():
    rows = [
        Row("1", "pt-PT", "plain", "x1", ".", "t", "gold"),
        Row("2", "pt-PT", "plain", "x2", "ˈkatu", "t", "gold"),
    ]
    backend = Table({"x1": "abc", "x2": "ˈkat"})
    with pytest.warns(UserWarning, match="row 1: expected_ipa '.' has no segments"):
        # row 2 alone: 1 deletion on 5 segments
        assert per_by_category(rows, backend) == {"plain": 1 / 5}
    with pytest.warns(UserWarning, match="row 1"):
        assert per_by_category(rows[:1], backend) == {}


def test_noise_is_the_largest_change_in_one_row():
    rows = [
        Row("1", "pt-PT", "plain", "x1", "ab", "t", "gold"),
        Row("2", "pt-PT", "plain", "x2", "abcd", "t", "gold"),
    ]
    before = Table({"x1": "ax", "x2": "abcd"})   # 1 and 0 edits
    after = Table({"x1": "ab", "x2": "ab"})      # 0 and 2 edits
    comparison = gate.compare_backends(rows, before, after)
    # 6 segments: the gain is (1 - 0) + (0 - 2) = -1, the largest row change is 2
    assert comparison.gain == {"plain": -1 / 6}
    assert comparison.noise == {"plain": 2 / 6}
    assert comparison.segments == {"plain": 6}


def _sentence(first, words):
    """A sentence IPA of *first* and *words* words "pa": 2 + 2 * words segments."""
    return " ".join([first] + ["pa"] * words)


def _text(i):
    """The text of row *i*, in letters only, so that orthography2ipa reads it without a warning."""
    return "ta" + "la" * i


SPREAD_ROWS = [Row(f"h{i}", "pt-PT", "homograph", _text(i), _sentence("so", 15), "t", "gold")
               for i in range(30)]


def make_spread_backend():
    """Reads each of 30 sentences of 32 segments with one wrong vowel until its stage runs."""
    return AblatableTable({_text(i): _sentence("su", 15) for i in range(30)}, {"homographs": _fix_homograph})


def test_homograph_stage_that_fixes_one_segment_in_each_of_30_rows_passes(tmp_path, capsys):
    code = _run(tmp_path, _fields(SPREAD_ROWS), "--stages", "homographs:homograph",
                backend=f"{__name__}:make_spread_backend")
    out = capsys.readouterr().out.splitlines()
    assert "gold: homographs  PASS  own homograph +0.0312 (noise 0.0010)  homograph +0.0312" in out
    assert code == 0
    report = stage_gain(SPREAD_ROWS, make_spread_backend(), ["homographs"], baseline=O2I)
    # 30 substitutions removed in 30 * 32 = 960 segments; at most 1 in one row
    assert report["homographs"].gain == {"homograph": 30 / 960}
    assert report["homographs"].noise == {"homograph": 1 / 960}
    assert verdict(report, "homographs", "homograph") is True


ONE_ROW_ROWS = [Row("h0", "pt-PT", "homograph", _text(0), "katus katus", "t", "gold")] + [
    Row(f"h{i}", "pt-PT", "homograph", _text(i), "katu", "t", "gold") for i in range(1, 30)]


def make_one_row_backend():
    """Reads every sentence right, but sentence h0 only with its stage."""
    table = {_text(i): "katu" for i in range(1, 30)} | {_text(0): "xxxxx katus"}
    return AblatableTable(table, {"one": lambda ipa: ipa.replace("xxxxx", "katus")})


def test_stage_that_fixes_five_segments_in_one_row_only_fails(tmp_path, capsys):
    code = _run(tmp_path, _fields(ONE_ROW_ROWS), "--stages", "one:homograph",
                backend=f"{__name__}:make_one_row_backend")
    out = capsys.readouterr().out.splitlines()
    assert "gold: one  FAIL  own homograph +0.0397 (noise 0.0397)  homograph +0.0397" in out
    assert code == 1
    report = stage_gain(ONE_ROW_ROWS, make_one_row_backend(), ["one"], baseline=O2I)
    # 5 substitutions removed in 10 + 29 * 4 = 126 segments, all of them in one row
    assert report["one"].gain == {"homograph": 5 / 126}
    assert report["one"].noise == {"homograph": 5 / 126}
    assert verdict(report, "one", "homograph") is False


def test_stage_that_only_breaks_one_row_is_no_gain():
    def break_h0(ipa):
        return "" if ipa == "h0" else ipa

    rows = [Row(f"h{i}", "pt-PT", "homograph", f"h{i}", f"h{i}", "t", "gold") for i in range(10)]
    report = stage_gain(rows, AblatableTable({}, {"bad": break_h0}), ["bad"], baseline=O2I)
    # 2 deletions added in 10 * 2 = 20 segments, all of them in one row
    assert report["bad"].gain == {"homograph": -2 / 20}
    assert report["bad"].noise == {"homograph": 2 / 20}
    assert verdict(report, "bad", "homograph") is False


CATEGORY_ROWS = 30
SENTENCE = "pa" * 10    # 20 segments


class Ablation:
    """Reads each text from *full*, or from *off[stage]* when that stage is switched off."""

    def __init__(self, full, off):
        self.full = full
        self.off = off

    def phonemize(self, text, lang):
        return [list(self.full[text])]

    def without(self, stage):
        if stage not in self.off:
            raise ValueError(f"no stage {stage!r}")
        return Table(self.full | self.off[stage])


S5_ROWS = [Row(f"{c}{k}", "pt-PT", c, f"{c}{k}", SENTENCE, "t", "gold")
           for c in gate.CATEGORIES for k in range(CATEGORY_ROWS)]


def make_s5_backend():
    """The numbers stage fixes 1 segment in each of 2 number rows. It deletes the whole
    sentence of row 0 in each of the 5 other categories."""
    others = [c for c in gate.CATEGORIES if c != "number"]
    full = {row.text: SENTENCE for row in S5_ROWS} | {f"{c}0": "" for c in others}
    off = {"number0": "b" + SENTENCE[1:], "number1": "b" + SENTENCE[1:]} | {f"{c}0": SENTENCE for c in others}
    return Ablation(full, {"numbers": off})


def test_stage_that_deletes_a_sentence_in_other_categories_fails(tmp_path, capsys, o2i_reads):
    report = stage_gain(S5_ROWS, make_s5_backend(), ["numbers"], baseline=Table({}))
    comparison = report["numbers"]
    # number: 2 substitutions removed in 30 * 20 = 600 segments, at most 1 in one row
    assert comparison.gain["number"] == 2 / 600
    assert comparison.noise["number"] == 1 / 600
    # each other category: one sentence of 20 segments deleted, 20/600 lost, against 1/600
    assert {c: g for c, g in comparison.gain.items() if c != "number"} == {
        c: -20 / 600 for c in gate.CATEGORIES if c != "number"}
    assert verdict(report, "numbers", "number") is False
    o2i_reads({row.text: SENTENCE for row in S5_ROWS})
    assert _run(tmp_path, _fields(S5_ROWS), "--stages", "numbers:number",
                backend=f"{__name__}:make_s5_backend") == 1
    out = capsys.readouterr().out
    assert "gold: numbers  FAIL  own number +0.0033 (noise 0.0017)" in out
    assert "numbers FAIL" in out.splitlines()[-1]


@pytest.mark.parametrize("damaged, expected", [("ka t", True), ("k t", False)])
def test_stage_may_lose_one_segment_in_another_category(damaged, expected):
    rows = GOLD + [Row("k", "pt-PT", "plain", "kata", "ka ta", "t", "gold")]

    def fix_and_damage(ipa):
        return damaged if ipa == "ka ta" else _fix_homograph(ipa)

    backend = AblatableTable(BASE | {"kata": "ka ta"}, {"homographs": fix_and_damage})
    report = stage_gain(rows, backend, ["homographs"], baseline=O2I)
    # plain holds 6 rows of 4 segments: "ka t" loses 1 of 24, "k t" loses 2 of 24
    assert report["homographs"].gain["plain"] == (-1 / 24 if expected else -2 / 24)
    assert verdict(report, "homographs", "homograph") is expected


# --- planted stages ---

def test_planted_good_stage_passes():
    report = stage_gain(GOLD, make_good_backend(), ["homographs"], baseline=O2I)
    # without the stage the 5 homograph rows hold 1 substitution in 4 segments each: 5/20
    assert report["homographs"].gain == {"plain": 0.0, "homograph": 0.25}
    assert report["homographs"].noise == {"plain": 0.0, "homograph": 1 / 20}
    assert report["full_vs_o2i"].gain == {"plain": 0.0, "homograph": 0.25}
    assert verdict(report, "homographs", "homograph") is True


def test_planted_bad_stage_that_deletes_a_word_fails():
    backend = AblatableTable(BASE, {"homographs": _fix_homograph, "drop": _drop_last_word})
    report = stage_gain(GOLD, backend, ["drop"], baseline=O2I)
    # the stage deletes 2 of 4 segments in all 10 rows: PER 10/20 with it, 0 without
    assert report["drop"].gain == {"plain": -0.5, "homograph": -0.5}
    assert verdict(report, "drop", "plain") is False


def test_stage_that_helps_its_category_but_breaks_another_fails():
    def fix_and_damage(ipa):
        return "pa" if ipa == PLAIN else _fix_homograph(ipa)

    backend = AblatableTable(BASE, {"homographs": fix_and_damage})
    report = stage_gain(GOLD, backend, ["homographs"], baseline=O2I)
    assert report["homographs"].gain == {"plain": -0.5, "homograph": 0.25}
    assert verdict(report, "homographs", "homograph") is False


def test_neutral_stage_is_within_noise_and_does_not_earn_its_place():
    backend = AblatableTable(BASE, {"homographs": _fix_homograph, "noop": _noop})
    report = stage_gain(GOLD, backend, ["noop"], baseline=O2I)
    assert report["noop"].gain == {"plain": 0.0, "homograph": 0.0}
    assert report["noop"].noise == {"plain": 0.0, "homograph": 0.0}
    assert verdict(report, "noop", "plain") is False


def test_backend_without_ablation_is_not_ablatable():
    report = stage_gain(GOLD, make_rigid_backend(), ["homographs"], baseline=O2I)
    assert report["homographs"] is None
    assert report["full_vs_o2i"].gain == {"plain": 0.0, "homograph": 0.25}
    assert verdict(report, "homographs", "homograph") is None


@pytest.mark.parametrize("gains, noise, segment_counts, expected", [
    # a gain equal to the noise is noise
    ({"own": 0.25, "other": 0.0}, {"own": 0.25, "other": 0.0}, {"own": 4, "other": 4}, False),
    # another category may lose one segment: 1 of 4
    ({"own": 0.5, "other": -0.25}, {"own": 0.25, "other": 0.25}, {"own": 4, "other": 4}, True),
    # two segments lost in one row of another category fail, though that row is the noise
    ({"own": 0.5, "other": -0.5}, {"own": 0.25, "other": 0.5}, {"own": 4, "other": 4}, False),
    # one segment is one segment of that category: 1 of 10
    ({"own": 0.5, "other": -0.1}, {"own": 0.25, "other": 0.1}, {"own": 4, "other": 10}, True),
    ({"own": 0.5, "other": -0.2}, {"own": 0.25, "other": 0.2}, {"own": 4, "other": 10}, False),
])
def test_verdict_boundaries(gains, noise, segment_counts, expected):
    assert verdict({"s": gate.Comparison(gains, noise, segment_counts)}, "s", "own") is expected


# --- tiers ---

def test_per_refuses_mixed_tiers():
    rows = GOLD + _rows([("plain", PLAIN, PLAIN, 1)], tier="silver")
    with pytest.raises(ValueError, match="tiers"):
        per_by_category(rows, O2I)


def _write_tsv(path, rows):
    lines = ["\t".join(COLUMNS)] + ["\t".join(fields) for fields in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fields(rows):
    return [(r.id, r.lang, r.category, r.text, r.expected_ipa, r.source, r.tier) for r in rows]


def test_silver_rows_never_count_toward_gold(tmp_path, capsys):
    # silver rows expect "xa ya": 4 substitutions on 4 segments with and without the stage
    silver = _rows([("homograph", HOMOGRAPH, "xa ya", 3)], tier="silver")
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, _fields(GOLD + silver))
    code = main(["--lang", "pt-PT", "--tsv", str(tsv), "--stages", "homographs:homograph",
                 "--backend", f"{__name__}:make_good_backend"])
    out = capsys.readouterr().out.splitlines()
    assert "gold: rows plain 5  homograph 5" in out
    assert ("gold: homographs  PASS  own homograph +0.2500 (noise 0.0500)  "
            "plain +0.0000  homograph +0.2500") in out
    assert "silver: rows homograph 3" in out
    assert ("silver: homographs  FAIL  own homograph +0.0000 (noise 0.0000)  "
            "homograph +0.0000") in out
    assert out[-1] == "gate: PASS"
    assert code == 0


def test_failing_gold_verdict_exits_1(tmp_path, capsys):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, _fields(GOLD))
    code = main(["--lang", "pt-PT", "--tsv", str(tsv), "--stages", "homographs:plain",
                 "--backend", f"{__name__}:make_good_backend"])
    out = capsys.readouterr().out.splitlines()
    assert any(line.startswith("gold: homographs  FAIL") for line in out)
    assert out[-1] == "gate: FAIL  homographs FAIL"
    assert code == 1


# --- command line ---

def _run(tmp_path, rows, *args, backend=f"{__name__}:make_good_backend", text=None):
    tsv = tmp_path / "pt-PT.tsv"
    if text is None:
        _write_tsv(tsv, rows)
    else:
        tsv.write_text(text, encoding="utf-8")
    return main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", backend, *args])


def test_cli_counts_rows_in_and_out(tmp_path, capsys):
    tsv = tmp_path / "pt-PT.tsv"
    good = _fields(GOLD[:2])
    _write_tsv(tsv, good + [
        ("a", "pt-BR", "plain", PLAIN, PLAIN, "t", "gold"),
        ("b", "pt-PT", "weather", PLAIN, PLAIN, "t", "gold"),
        ("c", "pt-PT", "plain", PLAIN, PLAIN, "t", "bronze"),
        ("d", "pt-PT", "plain", PLAIN, " ", "t", "gold"),
        ("e", "pt-PT", "plain"),
        ("f", "pt-PT", "plain", PLAIN, ".", "t", "gold"),
    ])
    rows, skipped = read_tsv(str(tsv), "pt-PT")
    assert [r.id for r in rows] == ["gold0", "gold1"]
    assert main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa",
                 "--allow-skips"]) == 1
    assert capsys.readouterr().out.splitlines()[0] == (
        "rows: read 8, scored 2, skipped 6 (column count 1, empty text or expected_ipa 2, "
        "other lang 1, unknown category 1, unknown tier 1)")


def test_read_tsv_strips_padded_fields(tmp_path):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, [(" 1 ", " pt-PT", "plain ", f" {PLAIN} ", f"{PLAIN} ", " t", "gold ")])
    rows, skipped = read_tsv(str(tsv), "pt-PT")
    assert rows == [Row("1", "pt-PT", "plain", PLAIN, PLAIN, "t", "gold")]
    assert not skipped


def test_cli_reads_a_file_with_a_byte_order_mark(tmp_path, capsys):
    text = "\ufeff" + "\n".join(["\t".join(COLUMNS)] + ["\t".join(f) for f in _fields(GOLD)]) + "\n"
    assert _run(tmp_path, None, "--stages", "homographs:homograph", text=text) == 0
    assert capsys.readouterr().out.splitlines()[0] == "rows: read 10, scored 10, skipped 0"


@pytest.mark.parametrize("bad_row, reason", [
    (("x", "pt-PT", "plian", PLAIN, PLAIN, "t", "gold"), "unknown category 1"),
    (("x", "pt-PT", "plain", PLAIN, PLAIN, "t", "Gold"), "unknown tier 1"),
    (("x", "pt-PT", "plain", PLAIN, PLAIN, "t"), "column count 1"),
    (("x", "pt-PT", "plain", "", PLAIN, "t", "gold"), "empty text or expected_ipa 1"),
    (("x", "pt-PT", "plain", PLAIN, ".", "t", "gold"), "empty text or expected_ipa 1"),
    (("gold0", "pt-PT", "plain", PLAIN, PLAIN, "t", "gold"), "duplicate id 1"),
    (("x", "pt-PT", "plain", GOLD[0].text, PLAIN, "t", "gold"), "duplicate text 1"),
    (("x", "pt-PT", "plain", GOLD[0].text, PLAIN, "t", "silver"), "duplicate text 1"),
])
def test_cli_fails_on_a_row_with_a_defect_unless_skips_are_allowed(tmp_path, capsys, bad_row, reason):
    rows = _fields(GOLD) + [bad_row]
    counts = f"rows: read 11, scored 10, skipped 1 ({reason})"
    assert _run(tmp_path, rows, "--stages", "homographs:homograph") == 1
    out = capsys.readouterr().out.splitlines()
    assert out == [counts, "gate: FAIL  1 skipped for a defect; fix the rows or pass --allow-skips"]
    assert _run(tmp_path, rows, "--stages", "homographs:homograph", "--allow-skips") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == counts
    assert out[-1] == "gate: PASS"


def test_cli_fails_when_a_gold_stage_is_not_ablatable(tmp_path, capsys):
    code = _run(tmp_path, [("1", "pt-PT", "plain", "o gato", "u ˈɡatu", "t", "gold")],
                "--stages", "homographs:homograph", backend="orthography2ipa")
    out = capsys.readouterr().out.splitlines()
    assert out[1:] == [
        "gold: rows plain 1",
        "gold: full_vs_o2i  plain +0.0000",
        "gold: homographs  not ablatable",
        "silver: no rows, no verdict",
        "gate: FAIL  homographs not ablatable",
    ]
    assert code == 1


def test_cli_fails_when_a_stage_has_no_rows_in_its_category(tmp_path, capsys):
    rows = _fields(_rows([("plain", PLAIN, PLAIN, 3)]))
    assert _run(tmp_path, rows, "--stages", "homographs:homograph") == 1
    out = capsys.readouterr().out.splitlines()
    assert "gold: homographs  no homograph rows, no verdict" in out
    assert out[-1] == "gate: FAIL  homographs has no homograph rows"


def test_cli_fails_when_no_stage_is_given(tmp_path, capsys):
    assert _run(tmp_path, _fields(GOLD)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "gate: FAIL  no stage given, use --stages"


def test_cli_fails_when_the_set_has_no_gold_rows(tmp_path, capsys):
    rows = _fields(_rows([("homograph", HOMOGRAPH, HOMOGRAPH, 5)], tier="silver"))
    assert _run(tmp_path, rows, "--stages", "homographs:homograph") == 1
    out = capsys.readouterr().out.splitlines()
    assert out[1] == "gold: no rows, no verdict"
    assert out[-1] == "gate: FAIL  no gold rows"


@pytest.fixture
def o2i_reads(monkeypatch):
    """Replace standalone orthography2ipa, the default baseline, with a fixed table."""
    def install(table):
        monkeypatch.setattr("scriptconv.phonemizers.o2ipa.Orthography2IPAPhonemizer", lambda: Table(table))
    return install


def make_worse_than_o2i_backend():
    """Reads plain text as nothing, and fixes the homograph in its stage."""
    return AblatableTable({PLAIN: "", HOMOGRAPH: "su lo"}, {"homographs": _fix_homograph})


def test_cli_fails_when_the_backend_is_worse_than_orthography2ipa(tmp_path, capsys, o2i_reads):
    o2i_reads({PLAIN: "ˈpɐ ˈtɐ", HOMOGRAPH: "su lo"})
    rows = _fields(_rows([("plain", PLAIN, "ˈpɐ ˈtɐ", 2), ("homograph", HOMOGRAPH, HOMOGRAPH, 2)]))
    code = _run(tmp_path, rows, "--stages", "homographs:homograph",
                backend=f"{__name__}:make_worse_than_o2i_backend")
    out = capsys.readouterr().out.splitlines()
    # The baseline reads "pa ta" right, 0 edits on 6 segments, and the backend reads it as
    # nothing, 6 deletions: 12/12 lost. The baseline reads "so lo" as "su lo", 1 substitution
    # on 4 segments, and the backend reads it right: 2/8 gained.
    assert out[2:] == [
        "gold: full_vs_o2i  plain -1.0000  homograph +0.2500",
        "gold: homographs  PASS  own homograph +0.2500 (noise 0.1250)  plain +0.0000  homograph +0.2500",
        "silver: no rows, no verdict",
        "gate: FAIL  full_vs_o2i plain -1.0000, the backend is worse than orthography2ipa",
    ]
    assert code == 1


def make_one_segment_worse_backend():
    """Reads "pa tax" with one extra segment, and fixes the homograph in its stage."""
    return AblatableTable(BASE, {"homographs": _fix_homograph})


def test_cli_fails_when_the_backend_is_one_segment_worse_than_orthography2ipa(tmp_path, capsys, o2i_reads):
    o2i_reads({"pa tax": PLAIN, HOMOGRAPH: HOMOGRAPH})
    rows = _rows([("plain", PLAIN, PLAIN, 24), ("homograph", HOMOGRAPH, HOMOGRAPH, 5)])
    rows.append(Row("long", "pt-PT", "plain", "pa tax", PLAIN, "t", "gold"))
    code = _run(tmp_path, _fields(rows), "--stages", "homographs:homograph",
                backend=f"{__name__}:make_one_segment_worse_backend")
    out = capsys.readouterr().out.splitlines()
    # 25 plain rows of 4 segments; the backend inserts 1 segment in one of them: -1/100
    assert "gold: full_vs_o2i  plain -0.0100  homograph +0.0000" in out
    assert out[-1] == "gate: FAIL  full_vs_o2i plain -0.0100, the backend is worse than orthography2ipa"
    assert code == 1


def test_cli_negative_silver_full_vs_o2i_does_not_fail_the_gate(tmp_path, capsys, o2i_reads):
    o2i_reads({"pa tax": PLAIN, HOMOGRAPH: HOMOGRAPH})
    rows = GOLD + _rows([("plain", "pa tax", PLAIN, 2)], tier="silver")
    code = _run(tmp_path, _fields(rows), "--stages", "homographs:homograph")
    out = capsys.readouterr().out.splitlines()
    # silver: the backend inserts 1 segment in each of 2 rows of 4 segments: -2/8
    assert "silver: full_vs_o2i  plain -0.2500" in out
    assert out[-1] == "gate: PASS"
    assert code == 0


def test_cli_fails_on_ten_copies_of_one_row(tmp_path, capsys):
    rows = [(f"h{i}", "pt-PT", "homograph", HOMOGRAPH, HOMOGRAPH, "t", "gold") for i in range(1, 11)]
    assert _run(tmp_path, rows, "--stages", "homographs:homograph") == 1
    assert capsys.readouterr().out.splitlines() == [
        "rows: read 10, scored 1, skipped 9 (duplicate text 9)",
        "gate: FAIL  9 skipped for a defect; fix the rows or pass --allow-skips"]
    scored, _ = read_tsv(str(tmp_path / "pt-PT.tsv"), "pt-PT")
    assert [row.id for row in scored] == ["h1"]
    # The first row alone: 1 substitution removed in 4 segments, all of it in one row
    assert _run(tmp_path, rows, "--stages", "homographs:homograph", "--allow-skips") == 1
    out = capsys.readouterr().out.splitlines()
    assert "gold: homographs  FAIL  own homograph +0.2500 (noise 0.2500)  homograph +0.2500" in out
    assert out[-1] == "gate: FAIL  homographs FAIL"


def test_cli_with_no_scored_row_exits_1(tmp_path, capsys):
    assert _run(tmp_path, [("1", "pt-BR", "plain", PLAIN, PLAIN, "t", "gold")], backend="orthography2ipa") == 1
    assert capsys.readouterr().out.splitlines() == [
        "rows: read 1, scored 0, skipped 1 (other lang 1)", "gate: FAIL  no row is scored"]


@pytest.mark.parametrize("args, message", [
    (["--backend", "orthography2ipa", "--stages", "homographs"], "give its category"),
    (["--backend", "no-such-backend"], "'no-such-backend' is not a valid Phonemizer"),
    (["--backend", "os:no_such_attribute"], "module 'os' has no attribute 'no_such_attribute'"),
    (["--backend", f"{__name__}:make_good_backend", "--stages", "nosuch:plain"], "no stage 'nosuch'"),
    (["--backend", f"{__name__}:make_good_backend", "--stages", "homographs:homograph,nosuch:plain"],
     "no stage 'nosuch'"),
])
def test_cli_usage_errors_exit_2_with_a_message(tmp_path, capsys, args, message):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, _fields(GOLD))
    with pytest.raises(SystemExit) as exit_info:
        main(["--lang", "pt-PT", "--tsv", str(tsv), *args])
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert message in captured.err
    assert captured.out == ""


def test_cli_rejects_a_missing_file(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--lang", "pt-PT", "--tsv", str(tmp_path / "nope.tsv"), "--backend", "orthography2ipa"])
    assert exit_info.value.code == 2
    assert "No such file or directory" in capsys.readouterr().err


def test_cli_rejects_a_wrong_header(tmp_path):
    tsv = tmp_path / "pt-PT.tsv"
    tsv.write_text("id\tlang\ttext\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa"])
    assert exit_info.value.code == 2
