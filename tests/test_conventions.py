import unicodedata
import unittest

from scriptconv import (
    CONVENTION_REGISTRY,
    apply,
    conventions_for,
    decompose_hangul,
    detect_convention,
    restyle,
    strip,
)


class TestRegistryInvariants(unittest.TestCase):
    def test_default_style_is_a_declared_style(self):
        for c in CONVENTION_REGISTRY.values():
            self.assertIn(c.default_style, c.styles, c.id)

    def test_sibling_conventions_on_same_script_have_disjoint_ranges(self):
        convs = list(CONVENTION_REGISTRY.values())
        for i, a in enumerate(convs):
            for b in convs[i + 1:]:
                if not set(a.scripts) & set(b.scripts):
                    continue
                a_cps = {cp for lo, hi in a.ranges for cp in range(lo, hi + 1)}
                b_cps = {cp for lo, hi in b.ranges for cp in range(lo, hi + 1)}
                self.assertFalse(a_cps & b_cps, f"{a.id} overlaps {b.id}")

    def test_strippable_conventions_declare_none_style(self):
        for c in CONVENTION_REGISTRY.values():
            if c.id == "jamo-form":
                self.assertNotIn("none", c.styles)  # no unmarked state exists
            else:
                self.assertIn("none", c.styles, c.id)

    def test_conventions_for_surfaces_system(self):
        latn = conventions_for("Latn")
        self.assertEqual([c.id for c in latn], ["pinyin-tone"])
        self.assertEqual(latn[0].system, "pinyin")

    def test_unknown_convention_raises_with_known_ids(self):
        with self.assertRaises(ValueError) as ctx:
            strip("x", "vowel-harmony")
        self.assertIn("tashkeel", str(ctx.exception))


class TestTashkeel(unittest.TestCase):
    def test_strips_full_vocalization(self):
        self.assertEqual(strip("مُحَمَّدٌ", "tashkeel"), "محمد")

    def test_nfd_hamza_and_madda_survive(self):
        # آ أ إ decomposed to alef + combining madda/hamza — letter identity,
        # must NOT be stripped
        nfd = unicodedata.normalize("NFD", "آمين أب إن")
        out = strip(nfd, "tashkeel")
        self.assertEqual(unicodedata.normalize("NFC", out), "آمين أب إن")

    def test_dagger_alif_stripped(self):
        self.assertEqual(strip("رحمٰن", "tashkeel"), "رحمن")

    def test_lone_shadda_detects_marked(self):
        self.assertEqual(detect_convention("plain text مدّ here", "tashkeel"), "marked")
        self.assertEqual(detect_convention("محمد", "tashkeel"), "none")

    def test_no_apply_transition(self):
        with self.assertRaises(ValueError):
            apply("محمد", "tashkeel")


class TestKashidaAndQuranic(unittest.TestCase):
    def test_kashida_stripped_independently_of_tashkeel(self):
        self.assertEqual(strip("محمـــد", "kashida"), "محمد")
        # tashkeel strip leaves tatweel alone
        self.assertEqual(strip("محمـــد", "tashkeel"), "محمـــد")

    def test_quranic_sajdah_sign_stripped(self):
        text = "قرأ۩"
        self.assertEqual(strip(text, "quranic-marks"), "قرأ")


class TestHebrew(unittest.TestCase):
    def test_niqqud_stripped_points_and_dagesh(self):
        self.assertEqual(strip("שָׁלוֹם", "niqqud"), "שלום")

    def test_maqaf_and_sof_pasuq_survive_both_strips(self):
        text = "כָּל־הָעוֹלָם׃"
        for conv in ("niqqud", "teamim"):
            out = strip(text, conv)
            self.assertIn("־", out)
            self.assertIn("׃", out)

    def test_teamim_stripped_niqqud_kept(self):
        # etnahta U+0591 removed, qamats U+05B8 kept
        text = "וַ֑יֹּאמֶר"
        out = strip(text, "teamim")
        self.assertNotIn("֑", out)
        self.assertIn("ַ", unicodedata.normalize("NFD", out))

    def test_detect_distinguishes_layers(self):
        pointed_only = "שָׁלוֹם"
        self.assertEqual(detect_convention(pointed_only, "niqqud"), "marked")
        self.assertEqual(detect_convention(pointed_only, "teamim"), "none")


class TestWakachigaki(unittest.TestCase):
    def test_strip_removes_spaces_between_japanese(self):
        self.assertEqual(strip("わたし は がくせい です", "wakachigaki"),
                         "わたしはがくせいです")

    def test_ideographic_space_stripped(self):
        self.assertEqual(strip("東京　大阪", "wakachigaki"), "東京大阪")

    def test_spaces_next_to_latin_survive(self):
        self.assertEqual(strip("きょうは good day", "wakachigaki"),
                         "きょうは good day")

    def test_spaces_next_to_digits_survive(self):
        self.assertEqual(strip("第 3 章", "wakachigaki"), "第 3 章")

    def test_not_detectable(self):
        self.assertIsNone(detect_convention("わたし は", "wakachigaki"))

    def test_apply_strip_round_trip_pure_japanese(self):
        text = "私は学生です"
        spaced = apply(text, "wakachigaki")
        self.assertIn(" ", spaced)
        self.assertEqual(strip(spaced, "wakachigaki"), text)


class TestPinyinTone(unittest.TestCase):
    def test_number_to_mark_basic(self):
        self.assertEqual(restyle("zhong1 guo2 ren2", "pinyin-tone", "mark"),
                         "zhōng guó rén")

    def test_umlaut_v_and_colon_variants(self):
        self.assertEqual(restyle("lv4 nu:3", "pinyin-tone", "mark"), "lǜ nǚ")

    def test_capitals_and_apostrophe(self):
        self.assertEqual(restyle("Xi1'an1", "pinyin-tone", "mark"), "Xī'ān")

    def test_erhua_and_syllabic_nasal(self):
        self.assertEqual(restyle("huar2", "pinyin-tone", "mark"), "huár")
        self.assertEqual(restyle("m2", "pinyin-tone", "mark"), "ḿ")

    def test_ou_placement_rule(self):
        self.assertEqual(restyle("gou3", "pinyin-tone", "mark"), "gǒu")
        self.assertEqual(restyle("guo2", "pinyin-tone", "mark"), "guó")
        self.assertEqual(restyle("jiu3", "pinyin-tone", "mark"), "jiǔ")

    def test_neutral_tone_unmarked(self):
        self.assertEqual(restyle("ma5 de0", "pinyin-tone", "mark"), "ma de")

    def test_mark_to_number_compliant(self):
        self.assertEqual(restyle("zhōng guó", "pinyin-tone", "number", frm="mark"),
                         "zhong1 guo2")
        self.assertEqual(restyle("Xī'ān", "pinyin-tone", "number", frm="mark"),
                         "Xi1'an1")

    def test_mark_to_number_unapostrophized_best_effort(self):
        # documented best-effort split: cut before the longest valid onset
        self.assertEqual(restyle("fāngān", "pinyin-tone", "number", frm="mark"),
                         "fan1gan1")

    def test_strip_handles_both_styles_and_spares_ordinary_digits(self):
        self.assertEqual(strip("Nǐ hǎo ma5", "pinyin-tone"), "Ni hao ma")
        self.assertEqual(strip("di4 3 ceng2", "pinyin-tone"), "di 3 ceng")

    def test_restyle_to_mark_infers_number_source(self):
        self.assertEqual(restyle("hao3", "pinyin-tone", "mark"), "hǎo")


class TestJamoForm(unittest.TestCase):
    def test_round_trip_byte_identical(self):
        compat = decompose_hangul("한국말")
        conj = restyle(compat, "jamo-form", "conjoining")
        self.assertEqual(restyle(conj, "jamo-form", "compatibility"), compat)

    def test_agrees_with_decompose_hangul(self):
        for word in ("안녕", "값", "한국말"):
            self.assertEqual(
                restyle(decompose_hangul(word), "jamo-form", "conjoining"),
                decompose_hangul(word, form="conjoining"))

    def test_detect_repertoire(self):
        self.assertEqual(detect_convention("ㄱㅏ", "jamo-form"), "compatibility")
        self.assertEqual(detect_convention("가", "jamo-form"), "conjoining")
        self.assertIsNone(detect_convention("hangul-free", "jamo-form"))

    def test_no_none_style(self):
        with self.assertRaises(ValueError):
            strip("ㄱㅏ", "jamo-form")


class TestRestyleContract(unittest.TestCase):
    def test_unsupported_transition_names_supported_ones(self):
        with self.assertRaises(ValueError) as ctx:
            restyle("x", "tashkeel", "marked", frm="none")
        self.assertIn("marked->none", str(ctx.exception))

    def test_same_style_is_identity(self):
        self.assertEqual(restyle("abc", "pinyin-tone", "mark", frm="mark"), "abc")

    def test_invalid_target_style_raises(self):
        with self.assertRaises(ValueError):
            restyle("abc", "pinyin-tone", "cyrillic")


if __name__ == "__main__":
    unittest.main()


class TestEncapsulation(unittest.TestCase):
    """Operations are fully driven by a convention's own transitions/detector."""

    def test_ad_hoc_convention_works_through_generic_operations(self):
        from scriptconv.conventions import Convention, Transition
        rot = Convention(
            "x-demo", "demo", ("Latn",), None, ("upper", "none"), "none", (),
            "test fixture",
            transitions=(Transition("none", "upper", str.upper),
                         Transition("upper", "none", str.lower)),
            detector=lambda t: "upper" if t.isupper() else "none")
        self.assertEqual(rot.apply("abc"), "ABC")
        self.assertEqual(rot.strip("ABC"), "abc")
        self.assertEqual(rot.detect("ABC"), "upper")
        self.assertEqual(rot.restyle("ABC", "none"), "abc")

    def test_wakachigaki_apply_requires_is_queryable(self):
        conv = CONVENTION_REGISTRY["wakachigaki"]
        self.assertEqual(conv.apply_requires, "ja")
        self.assertIsNone(CONVENTION_REGISTRY["tashkeel"].apply_requires)

    def test_jamo_form_strip_lossless_derived_from_transitions(self):
        self.assertFalse(CONVENTION_REGISTRY["tashkeel"].strip_lossless)
        self.assertFalse(CONVENTION_REGISTRY["jamo-form"].strip_lossless)  # no "none" transitions
        self.assertTrue(all(t.lossless for t in
                            CONVENTION_REGISTRY["jamo-form"].transitions))
