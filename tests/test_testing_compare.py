"""Tests for the sentence gate, scriptconv.testing.compare.

Every expected PER below is an edit distance counted by hand on the strings in
the test, never a value read back from the harness.
"""
import pytest

from scriptconv.testing.compare import (
    COLUMNS, Row, edit_distance, main, noise_by_category, per_by_category,
    read_tsv, segments, stage_gain, verdict,
)

PLAIN = "pa ta"      # 4 segments, every backend reads it right
HOMOGRAPH = "so lo"  # 4 segments; the backend reads "su lo" until its homograph stage runs


def _fix_homograph(ipa):
    return ipa.replace("su", "so")


def _drop_last_word(ipa):
    return ipa.rsplit(" ", 1)[0]


def _noop(ipa):
    return ipa


class Table:
    """A backend that reads a text through a fixed table, then runs its stages in order."""

    def __init__(self, table, stages=None):
        self.table = table
        self.stages = dict(stages or {})

    def phonemize(self, text, lang):
        ipa = self.table.get(text, text)
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
    """Rows from (category, text, expected_ipa, count) tuples."""
    rows = []
    for category, text, expected, count in spec:
        for _ in range(count):
            rows.append(Row(str(len(rows)), "pt-PT", category, text, expected, "test", tier))
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


def test_noise_is_one_sentence_share_per_category():
    rows = _rows([("plain", PLAIN, PLAIN, 4), ("homograph", HOMOGRAPH, HOMOGRAPH, 2)])
    assert noise_by_category(rows) == {"plain": 0.25, "homograph": 0.5}


# --- planted stages ---

def test_planted_good_stage_passes():
    report = stage_gain(GOLD, make_good_backend(), ["homographs"], baseline=O2I)
    # without the stage the 5 homograph rows hold 1 substitution in 4 segments each: 5/20
    assert report["homographs"] == {"plain": 0.0, "homograph": 0.25}
    assert report["full_vs_o2i"] == {"plain": 0.0, "homograph": 0.25}
    assert verdict(report, "homographs", "homograph", noise_by_category(GOLD)) is True


def test_planted_bad_stage_that_deletes_a_word_fails():
    backend = AblatableTable(BASE, {"homographs": _fix_homograph, "drop": _drop_last_word})
    report = stage_gain(GOLD, backend, ["drop"], baseline=O2I)
    # the stage deletes 2 of 4 segments in all 10 rows: PER 10/20 with it, 0 without
    assert report["drop"] == {"plain": -0.5, "homograph": -0.5}
    assert verdict(report, "drop", "plain", noise_by_category(GOLD)) is False


def test_stage_that_helps_its_category_but_breaks_another_fails():
    def fix_and_damage(ipa):
        return "pa" if ipa == PLAIN else _fix_homograph(ipa)

    backend = AblatableTable(BASE, {"homographs": fix_and_damage})
    report = stage_gain(GOLD, backend, ["homographs"], baseline=O2I)
    assert report["homographs"] == {"plain": -0.5, "homograph": 0.25}
    assert verdict(report, "homographs", "homograph", noise_by_category(GOLD)) is False


def test_neutral_stage_is_within_noise_and_does_not_earn_its_place():
    backend = AblatableTable(BASE, {"homographs": _fix_homograph, "noop": _noop})
    report = stage_gain(GOLD, backend, ["noop"], baseline=O2I)
    noise = noise_by_category(GOLD)
    assert report["noop"] == {"plain": 0.0, "homograph": 0.0}
    assert all(abs(gain) <= noise[c] for c, gain in report["noop"].items())
    assert verdict(report, "noop", "plain", noise) is False


def test_backend_without_ablation_is_not_ablatable():
    report = stage_gain(GOLD, make_rigid_backend(), ["homographs"], baseline=O2I)
    assert report["homographs"] is None
    assert report["full_vs_o2i"] == {"plain": 0.0, "homograph": 0.25}
    assert verdict(report, "homographs", "homograph", 0.2) is None


@pytest.mark.parametrize("gains, noise, expected", [
    ({"own": 0.25, "other": 0.0}, 0.25, False),     # a gain equal to noise is noise
    ({"own": 0.5, "other": -0.25}, 0.25, True),     # a loss equal to noise is noise
    ({"own": 0.5, "other": -0.5}, 0.25, False),
    ({"own": 0.5, "other": -0.5}, {"own": 0.25, "other": 0.5}, True),   # noise per category
    ({"own": 0.5, "other": -0.5}, {"own": 0.75, "other": 0.5}, False),
])
def test_verdict_boundaries(gains, noise, expected):
    assert verdict({"s": gains}, "s", "own", noise) is expected


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
    assert ("gold: homographs  PASS  own homograph +0.2500 (noise 0.2000)  "
            "plain +0.0000  homograph +0.2500") in out
    assert "silver: rows homograph 3" in out
    assert ("silver: homographs  FAIL  own homograph +0.0000 (noise 0.3333)  "
            "homograph +0.0000") in out
    assert code == 0


def test_failing_gold_verdict_exits_1(tmp_path, capsys):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, _fields(GOLD))
    code = main(["--lang", "pt-PT", "--tsv", str(tsv), "--stages", "homographs:plain",
                 "--backend", f"{__name__}:make_good_backend"])
    assert "gold: homographs  FAIL" in capsys.readouterr().out
    assert code == 1


# --- command line ---

def test_cli_counts_rows_in_and_out(tmp_path, capsys):
    tsv = tmp_path / "pt-PT.tsv"
    good = _fields(GOLD[:2])
    _write_tsv(tsv, good + [
        ("a", "pt-BR", "plain", PLAIN, PLAIN, "t", "gold"),
        ("b", "pt-PT", "weather", PLAIN, PLAIN, "t", "gold"),
        ("c", "pt-PT", "plain", PLAIN, PLAIN, "t", "bronze"),
        ("d", "pt-PT", "plain", PLAIN, " ", "t", "gold"),
        ("e", "pt-PT", "plain"),
    ])
    rows, skipped = read_tsv(str(tsv), "pt-PT")
    assert [r.id for r in rows] == ["0", "1"]
    assert main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == (
        "rows: read 7, scored 2, skipped 5 (column count 1, empty text or expected_ipa 1, "
        "other lang 1, unknown category 1, unknown tier 1)")


def test_cli_with_default_baseline_reports_no_gain_for_orthography2ipa(tmp_path, capsys):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, [("1", "pt-PT", "plain", "o gato", "u ˈɡatu", "t", "gold")])
    code = main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa",
                 "--stages", "homographs:homograph"])
    out = capsys.readouterr().out.splitlines()
    assert out[1:] == [
        "gold: rows plain 1",
        "gold: full_vs_o2i  plain +0.0000",
        "gold: homographs  not ablatable",
        "silver: no rows, no verdict",
    ]
    assert code == 0


def test_cli_rejects_a_stage_with_no_category(tmp_path):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, _fields(GOLD))
    with pytest.raises(SystemExit):
        main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa",
              "--stages", "homographs"])


def test_cli_rejects_a_wrong_header(tmp_path):
    tsv = tmp_path / "pt-PT.tsv"
    tsv.write_text("id\tlang\ttext\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa"])


def test_cli_rejects_an_unknown_backend(tmp_path):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, _fields(GOLD))
    with pytest.raises(SystemExit) as exit_info:
        main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "no-such-backend"])
    assert exit_info.value.code == 2


def test_cli_with_no_scored_row_exits_1(tmp_path, capsys):
    tsv = tmp_path / "pt-PT.tsv"
    _write_tsv(tsv, [("1", "pt-BR", "plain", PLAIN, PLAIN, "t", "gold")])
    assert main(["--lang", "pt-PT", "--tsv", str(tsv), "--backend", "orthography2ipa"]) == 1
    assert capsys.readouterr().out.splitlines() == ["rows: read 1, scored 0, skipped 1 (other lang 1)"]
