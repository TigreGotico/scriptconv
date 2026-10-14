# -*- coding: UTF8 -*-
"""Phonetisation core ported from Iqra-Eval/MSA_phonetiser's
``phonetiser/phonetise_Arabic.py`` (https://github.com/Iqra-Eval/MSA_phonetiser),
the IqraEval shared task's own published data-prep code — see this
directory's LICENSE.md for the CC BY-NC 4.0 provenance chain (nawarhalabi's
original Arabic-Phonetiser -> the IqraEval fork -> this trim).

Trimmed from the original: the stress-boundary annotation path
(``findStressIndex``/``utterancesPronuncationsWithBoundaries``) is dropped —
``run_phonetiser.py``'s own ``get_phoneme()`` only ever reads
``phonetise(text)[1]`` (the plain, non-stress-annotated pronunciation list),
so dropping it changes nothing observable and spares vendoring
``phonetiser/findstress.py`` for a feature ``phoneme_ref`` never used
(arbtok's ``scripts/benchmark_iqraeval.py`` independently confirms "no
silence, pause, or explicit stress token appears in the sample"). The
CLI/file-I/O wrapper (the original file's ``if __name__ == "__main__":``
block) is dropped too — scriptconv calls ``phonetise()`` directly.

## Why this file exists next to mantoq's own vendored copy

Diffing this fork against both nawarhalabi's original upstream
(github.com/nawarhalabi/Arabic-Phonetiser/blob/master/phonetise-Buckwalter.py)
and mantoq's vendored ``buck/phonetise_buckwalter.py``
(``scriptconv/phonemizers/_vendored/mantoq/``) surfaced the root causes of
every major residual mismatch class ``Phonemizer.IQRA`` had against
``IqraEval/Iqra_train``'s ``phoneme_ref`` before this file was ported in
(see the PR that introduced it for the full methodology and match-rate
history):

1. **mantoq's copy delegates Arabic<->Buckwalter transliteration to
   ``scriptconv.notation``'s *standard* Buckwalter table**, which encodes
   "th" (ث) as ``v`` (the Tim Buckwalter scheme). Nawar Halabi's OWN
   phonetiser — both the pristine upstream file and this IqraEval fork —
   was written against his own non-standard variant, where ث is ``^``
   (verified: this is the ONLY letter the two schemes disagree on, diffed
   character-by-character). ``v`` isn't in ``unambiguousConsonantMap`` at
   all in either variant (there it names an unrelated loanword phone), so
   every ث silently vanished when phonetised through mantoq's copy. This
   file's own ``arabic_to_buckwalter`` (below) is Halabi's original
   inline dict, so the bug cannot occur here.
2. **The word-initial "kaf/wāw + alif" ambiguity** (upstream/mantoq:
   ``letter=="A" and letter_1 in ("w","k") and letter_2=="b"``, matching
   *any* word starting with ك or و immediately followed by alif — e.g.
   "كَانَ" kāna — and defaulting its first-generated pronunciation to the
   short-vowel reading) is narrowed here to
   ``letter=="A" and letter_1 in ("w","k") and letter_2=="b" and letter1=="l"``:
   only "كال-"/"وال-" (preposition + definite article) is genuinely
   ambiguous; "كان" and similar words are just unconditionally long, as
   real Arabic orthography says an alif always is.
3. **Wāw al-jamāʿah's silent alif** (masculine-plural verb ending, "-وا"):
   the ambiguous-candidate order is swapped so the *elided* alif is the
   default (index 0) reading, rather than upstream/mantoq's *pronounced*
   default — matching how the alif there is a purely orthographic marker.
4. **Sun-letter lam-omission** is restricted to firing only when the lam
   is genuinely part of "ال" or is word-initial on its own
   (``letter_1 in ("A", "l", "b")`` guard added), rather than any lam
   anywhere immediately before a shadda-doubled consonant.

None of these are hypothetical: (1)-(3) are diff-verified against the
IqraEval fork's actual source; whether (4) reproduces `phoneme_ref`'s
practice of never eliding the definite article's lam even before a sun
letter is verified empirically (see the benchmark script).
"""

# ----------------------------------------------------------------------------
# Arabic <-> Buckwalter — Halabi's OWN scheme (NOT scriptconv.notation's
# standard-Buckwalter table: this is the one letter it disagrees with — ث is
# "^" here, "v" in the standard scheme — see the module docstring, point 1).
# ----------------------------------------------------------------------------
buckwalter = {
    "ب": "b", "ذ": "*", "ط": "T", "م": "m",
    "ت": "t", "ر": "r", "ظ": "Z", "ن": "n",
    "ث": "^", "ز": "z", "ع": "E", "ه": "h",
    "ج": "j", "س": "s", "غ": "g", "ح": "H",
    "ق": "q", "ف": "f", "خ": "x", "ص": "S",
    "ش": "$", "د": "d", "ض": "D", "ك": "k",
    "أ": ">", "ء": "'", "ئ": "}", "ؤ": "&",
    "إ": "<", "آ": "|", "ا": "A", "ى": "Y",
    "ة": "p", "ي": "y", "ل": "l", "و": "w",
    "ً": "F", "ٌ": "N", "ٍ": "K", "َ": "a",
    "ُ": "u", "ِ": "i", "ّ": "~", "ْ": "o",
}


def arabic_to_buckwalter(word: str) -> str:
    return "".join(buckwalter.get(letter, letter) for letter in word)


# ----------------------------------------------------------------------------
# Grapheme to Phoneme mappings (identical to upstream/mantoq except point 2
# and point 3 in the module docstring, both marked below)
# ----------------------------------------------------------------------------
unambiguousConsonantMap = {
    "b": "b", "*": "*", "T": "T", "m": "m",
    "t": "t", "r": "r", "Z": "Z", "n": "n",
    "^": "^", "z": "z", "E": "E", "h": "h",
    "j": "j", "s": "s", "g": "g", "H": "H",
    "q": "q", "f": "f", "x": "x", "S": "S",
    "$": "$", "d": "d", "D": "D", "k": "k",
    ">": "<", "'": "<", "}": "<", "&": "<",
    "<": "<",
}

ambiguousConsonantMap = {
    "l": ["l", ""], "w": "w", "y": "y", "p": ["t", ""],
}

maddaMap = {"|": [["<", "aa"], ["<", "AA"]]}

vowelMap = {
    "A": [["aa", ""], ["AA", ""]], "Y": [["aa", ""], ["AA", ""]],
    "w": [["uu0", "uu1"], ["UU0", "UU1"]],
    "y": [["ii0", "ii1"], ["II0", "II1"]],
    "a": ["a", "A"],
    "u": [["u0", "u1"], ["U0", "U1"]],
    "i": [["i0", "i1"], ["I0", "I1"]],
}

diacritics = ["o", "a", "u", "i", "F", "N", "K", "~"]
diacriticsWithoutShadda = ["o", "a", "u", "i", "F", "N", "K"]
emphatics = ["D", "S", "T", "Z", "g", "x", "q"]
forwardEmphatics = ["g", "x"]
consonants = [">", "<", "}", "&", "'", "b", "t", "^", "j", "H", "x", "d", "*",
              "r", "z", "s", "$", "S", "D", "T", "Z", "E", "g", "f", "q", "k",
              "l", "m", "n", "h", "|"]

# ------------------------------------------------------------------------------------
# Words with fixed irregular pronunciations (the IqraEval fork's expanded table:
# preposition-prefixed variants of the same fixed words)
# ------------------------------------------------------------------------------------
fixedWords = {
    "h*A": ["h aa * aa", "h aa * a"],
    "bh*A": ["b i0 h aa * aa", "b i0 h aa * a"],
    "kh*A": ["k a h aa * aa", "k a h aa * a"],
    "fh*A": ["f a h aa * aa", "f a h aa * a"],
    "h*h": ["h aa * i0 h i0", "h aa * i1 h"],
    "bh*h": ["b i0 h aa * i0 h i0", "b i0 h aa * i1 h"],
    "kh*h": ["k a h aa * i0 h i0", "k a h aa * i1 h"],
    "fh*h": ["f a h aa * i0 h i0", "f a h aa * i1 h"],
    "h*An": ["h aa * aa n i0", "h aa * aa n"],
    "h&lA'": ["h aa < u0 l aa < i0", "h aa < u0 l aa <"],
    "*lk": ["* aa l i0 k a", "* aa l i0 k"],
    "b*lk": ["b i0 * aa l i0 k a", "b i0 * aa l i0 k"],
    "k*lk": ["k a * aa l i0 k a", "k a * aa l i1 k"],
    "*lkm": "* aa l i0 k u1 m",
    ">wl}k": ["< u0 l aa < i0 k a", "< u0 l aa < i1 k"],
    "Th": "T aa h a",
    "lkn": ["l aa k i0 nn a", "l aa k i1 n"],
    "lknh": "l aa k i0 nn a h u0",
    "lknhm": "l aa k i0 nn a h u1 m",
    "lknk": ["l aa k i0 nn a k a", "l aa k i0 nn a k i0"],
    "lknkm": "l aa k i0 nn a k u1 m",
    "lknkmA": "l aa k i0 nn a k u0 m aa",
    "lknnA": "l aa k i0 nn a n aa",
    "AlrHmn": ["rr a H m aa n i0", "rr a H m aa n"],
    "Allh": ["ll aa h i0", "ll aa h", "ll AA h u0", "ll AA h a", "ll AA h", "ll A"],
    "h*yn": ["h aa * a y n i0", "h aa * a y n"],
    "wh*A": ["w a h aa * aa", "w a h aa * a"],
    "wbh*A": ["w a b i0 h aa * aa", "w a b i0 h aa * a"],
    "wkh*A": ["w a k a h aa * aa", "w a k a h aa * a"],
    "wh*h": ["w a h aa * i0 h i0", "w a h aa * i1 h"],
    "wbh*h": ["w a b i0 h aa * i0 h i0", "w a b i0 h aa * i1 h"],
    "wkh*h": ["w a k a h aa * i0 h i0", "w a k a h aa * i1 h"],
    "wh*An": ["w a h aa * aa n i0", "w a h aa * aa n"],
    "wh&lA'": ["w a h aa < u0 l aa < i0", "w a h aa < u0 l aa <"],
    "w*lk": ["w a * aa l i0 k a", "w a * aa l i0 k"],
    "wb*lk": ["w a b i0 * aa l i0 k a", "w a b i0 * aa l i0 k"],
    "wk*lk": ["w a k a * aa l i0 k a", "w a k a * aa l i1 k"],
    "w*lkm": "w a * aa l i0 k u1 m",
    "w>wl}k": ["w a < u0 l aa < i0 k a", "w a < u0 l aa < i1 k"],
    "wTh": "w a T aa h a",
    "wlkn": ["w a l aa k i0 nn a", "w a l aa k i1 n"],
    "wlknh": "w a l aa k i0 nn a h u0",
    "wlknhm": "w a l aa k i0 nn a h u1 m",
    "wlknk": ["w a l aa k i0 nn a k a", "w a l aa k i0 nn a k i0"],
    "wlknkm": "w a l aa k i0 nn a k u1 m",
    "wlknkmA": "w a l aa k i0 nn a k u0 m aa",
    "wlknnA": "w a l aa k i0 nn a n aa",
    "wAlrHmn": ["w a rr a H m aa n i0", "w a rr a H m aa n"],
    "wAllh": ["w a ll aa h i0", "w a ll aa h", "w a ll AA h u0", "w a ll AA h a",
              "w a ll AA h", "w a ll A"],
    "wh*yn": ["w a h aa * a y n i0", "w a h aa * a y n"],
    "Aw": ["< a w"],
    ">w": ["< a w"],
    "Alf": ["< a l f"],
    ">lf": ["< a l f"],
    "b>lf": ["b i0 < a l f"],
    "f>lf": ["f a < a l f"],
    "wAlf": ["w a < a l f"],
    "w>lf": ["w a < a l f"],
    "wb>lf": ["w a b i0 < a l f"],
    "nt": "n i1 t",
    "fydyw": "v i0 d y uu1",
    "lndn": "l A n d u1 n",
}


def isFixedWord(word, results, pronunciations):
    lastLetter = ""
    if len(word) > 0:
        lastLetter = word[-1]
    if lastLetter == "a":
        lastLetter = ["a", "A"]
    elif lastLetter == "A":
        lastLetter = ["aa"]
    elif lastLetter == "u":
        lastLetter = ["u0"]
    elif lastLetter == "i":
        lastLetter = ["i0"]
    elif lastLetter in unambiguousConsonantMap:
        lastLetter = [unambiguousConsonantMap[lastLetter]]
    import re as _re
    wordConsonants = _re.sub(r"[^h*Ahn'>wl}kmyTtfdb]", "", word)
    if wordConsonants in fixedWords:
        entry = fixedWords[wordConsonants]
        if isinstance(entry, list):
            done = False
            for pronunciation in entry:
                if pronunciation.split(" ")[-1] in lastLetter:
                    results += word + " " + pronunciation + "\n"
                    pronunciations.append(pronunciation.split(" "))
                    done = True
            if not done:
                results += word + " " + entry[0] + "\n"
                pronunciations.append(entry[0].split(" "))
        else:
            results += word + " " + entry + "\n"
            pronunciations.append(entry.split(" "))
    return results


def _process_word(word: str) -> list:
    """Phonetise one already-normalized Buckwalter word (no spaces), return
    its most likely pronunciation as a list of phones — the ``pronunciations[0]``
    the original always appends to ``utterancesPronuncations``."""
    pronunciations = []
    isFixedWord(word, "", pronunciations)

    emphaticContext = False
    padded = "bb" + word + "ee"
    phones = []

    for index in range(2, len(padded) - 2):
        letter = padded[index]
        letter1 = padded[index + 1]
        letter2 = padded[index + 2]
        letter_1 = padded[index - 1]
        letter_2 = padded[index - 2]

        # Upstream's condition here is ``not in emphatics + [u'r'""", u'l'"""]``
        # (both the pristine original and the IqraEval fork, byte-identical) —
        # an adjacent-string-literal typo that concatenates to the single,
        # never-matching string "r, u'l'" rather than the two single letters
        # the comment ("except for Lam and Ra") clearly intends. The actual
        # behavior this typo produces is what generated ``phoneme_ref``, so
        # it is reproduced verbatim here (i.e. "r"/"l" do NOT get an
        # exception — any non-emphatic consonant resets emphaticContext);
        # do not "fix" this to match the comment, it would only regress the
        # match rate against phoneme_ref (see the introducing PR's benchmark
        # history).
        if letter in consonants + ["w", "y"] and letter not in emphatics:
            emphaticContext = False
        if letter in emphatics:
            emphaticContext = True
        if letter1 in emphatics and letter1 not in forwardEmphatics:
            emphaticContext = True

        if letter in unambiguousConsonantMap:
            phones += [unambiguousConsonantMap[letter]]

        if letter == "l":
            # point 4: lam-omission (sun letters) restricted to genuine "ال"
            # / word-initial lam, not any lam before a shadda-doubled letter.
            if ((letter1 not in diacritics and letter1 not in vowelMap)
                    and letter2 == "~"
                    and (letter_1 in ("A", "l", "b")
                         or (letter_1 in diacritics and letter_2 in ("A", "l", "b")))):
                phones += [ambiguousConsonantMap["l"][1]]
            else:
                phones += [ambiguousConsonantMap["l"][0]]

        if letter == "~" and letter_1 not in ("w", "y") and len(phones) > 0:
            phones[-1] += phones[-1]

        if letter == "|":
            phones += [maddaMap["|"][1] if emphaticContext else maddaMap["|"][0]]

        if letter == "p":
            phones += [ambiguousConsonantMap["p"][0] if letter1 in diacritics
                      else ambiguousConsonantMap["p"][1]]

        if letter in vowelMap:
            if letter in ("w", "y"):
                if (letter1 in diacriticsWithoutShadda + ["A", "Y"]
                        or (letter1 in ("w", "y") and letter2 not in diacritics + ["A", "w", "y"])
                        or (letter_1 in diacriticsWithoutShadda and letter1 in consonants + ["e"])):
                    if ((letter == "w" and letter_1 == "u" and letter1 not in ("a", "i", "A", "Y"))
                            or (letter == "y" and letter_1 == "i" and letter1 not in ("a", "u", "A", "Y"))):
                        phones += [vowelMap[letter][1][0] if emphaticContext else vowelMap[letter][0][0]]
                    else:
                        if letter1 == "A" and letter == "w" and letter2 == "e":
                            phones += [[vowelMap[letter][0][0], ambiguousConsonantMap[letter]]]
                        else:
                            phones += [ambiguousConsonantMap[letter]]
                elif letter1 == "~":
                    if (letter_1 == "a" or (letter == "w" and letter_1 in ("i", "y"))
                            or (letter == "y" and letter_1 in ("w", "u"))):
                        phones += [ambiguousConsonantMap[letter], ambiguousConsonantMap[letter]]
                    else:
                        phones += [vowelMap[letter][0][0], ambiguousConsonantMap[letter]]
                else:
                    if emphaticContext:
                        if letter_1 in consonants + ["u", "i"] and letter1 == "e":
                            phones += [[vowelMap[letter][1][0], vowelMap[letter][1][0][1:]]]
                        else:
                            phones += [vowelMap[letter][1][0]]
                    else:
                        if letter_1 in consonants + ["u", "i"] and letter1 == "e":
                            phones += [[vowelMap[letter][0][0], vowelMap[letter][0][0][1:]]]
                        else:
                            phones += [vowelMap[letter][0][0]]
            if letter in ("u", "i"):
                if emphaticContext:
                    if (letter1 in unambiguousConsonantMap or letter1 == "l") and letter2 == "e" and len(padded) > 7:
                        phones += [vowelMap[letter][1][1]]
                    else:
                        phones += [vowelMap[letter][1][0]]
                else:
                    if (letter1 in unambiguousConsonantMap or letter1 == "l") and letter2 == "e" and len(padded) > 7:
                        phones += [vowelMap[letter][0][1]]
                    else:
                        phones += [vowelMap[letter][0][0]]
            if letter in ("a", "A", "Y"):
                # point 2: word-initial kaf/waw+alif ambiguity restricted to
                # "-al" (preposition + definite article), not every such word.
                if letter == "A" and letter_1 in ("w", "k") and letter_2 == "b" and letter1 == "l":
                    phones += [["a", vowelMap[letter][0][0]]]
                elif letter == "A" and letter_1 in ("u", "i"):
                    pass
                elif letter == "A" and letter_1 == "w" and letter1 == "e":
                    # point 3: wāw al-jamāʿah — elided alif is the default.
                    phones += [[vowelMap[letter][0][1], vowelMap[letter][0][0]]]
                elif letter in ("A", "Y") and letter1 == "e":
                    if emphaticContext:
                        phones += [[vowelMap[letter][1][0], vowelMap["a"][1]]]
                    else:
                        phones += [[vowelMap[letter][0][0], vowelMap["a"][0]]]
                else:
                    phones += [vowelMap[letter][1][0] if emphaticContext else vowelMap[letter][0][0]]

    possibilities = 1
    for p in phones:
        if isinstance(p, list):
            possibilities *= len(p)

    all_pronunciations = []
    for i in range(possibilities):
        pronunciation = []
        iterations = 1
        for p in phones:
            if isinstance(p, list):
                curIndex = (i // iterations) % len(p)
                if p[curIndex] != "":
                    pronunciation.append(p[curIndex])
                iterations *= len(p)
            else:
                if p != "":
                    pronunciation.append(p)
        all_pronunciations.append(pronunciation)

    if pronunciations:
        # a fixed-word pronunciation, when found, wins outright (matches the
        # original: isFixedWord already populated `pronunciations` and the
        # main loop's own phones list is generated independently but never
        # consulted when a fixed entry exists — see phonetise_Arabic.py).
        chosen = pronunciations[0]
    else:
        chosen = all_pronunciations[0] if all_pronunciations else []

    # House-keeping: remove duplicate vowels / duplicate y,w (verbatim).
    prevLetter = ""
    toDelete = []
    for i in range(len(chosen)):
        letter = chosen[i]
        if letter in ("aa", "uu0", "ii0", "AA", "UU0", "II0") and prevLetter.lower() == letter[1:].lower():
            toDelete.append(i - 1)
            chosen[i] = chosen[i - 1][0] + chosen[i - 1]
        if letter in ("u0", "i0") and prevLetter.lower() == letter.lower():
            toDelete.append(i - 1)
            chosen[i] = chosen[i - 1]
        if letter in ("y", "w") and prevLetter == letter:
            chosen[i - 1] += chosen[i - 1]
            toDelete.append(i)
        if letter == "a" and prevLetter == letter:
            toDelete.append(i)
        prevLetter = letter
    for i in reversed(sorted(set(toDelete))):
        del chosen[i]
    return chosen


import re as _re2


def _preprocess_utterance(utterance: str) -> list:
    """Utterance-level normalization from the fork's ``phonetise()``, run on
    the whole Buckwalter-encoded utterance BEFORE splitting into words and
    running :func:`_process_word` on each. This was dropped in an earlier,
    incomplete port of this file — its absence let a mid-utterance
    word-initial alif (the connecting hamzat al-waṣl of "ال"/"ا", silent in
    continuous recitation) get phonetised as a spurious long "aa", among
    other regressions (see the introducing PR's benchmark history for the
    match-rate collapse this caused and the fix). Ported verbatim from
    Iqra-Eval/MSA_phonetiser's ``phonetiser/phonetise_Arabic.py``.
    """
    utterance = utterance.replace("AF", "F")
    utterance = utterance.replace("ـ", "")  # tatweel
    utterance = utterance.replace("o", "")  # sukun: purely orthographic here
    utterance = utterance.replace("aA", "A")
    utterance = utterance.replace("aY", "Y")
    utterance = _re2.sub(r"([^\-]) A", r"\1 ", utterance)
    utterance = utterance.replace("F", "an")
    utterance = utterance.replace("N", "un")
    utterance = utterance.replace("K", "in")
    utterance = utterance.replace("|", ">A")

    utterance = _re2.sub(r"^Ai", "<i", utterance)
    utterance = _re2.sub(r"^Aa", ">a", utterance)
    utterance = _re2.sub(r"^Au", ">u", utterance)
    utterance = _re2.sub(r"Ai", "<i", utterance)
    utterance = _re2.sub(r"Aa", ">a", utterance)
    utterance = _re2.sub(r"Au", ">u", utterance)
    utterance = _re2.sub(r"^Al", ">al", utterance)
    utterance = _re2.sub(r" - Al", " - >al", utterance)
    utterance = _re2.sub(r"^- Al", "- >al", utterance)
    utterance = _re2.sub(r"^>([^auAw])", ">a\\1", utterance)
    utterance = _re2.sub(r" >([^auAw ])", " >a\\1", utterance)
    utterance = _re2.sub(r"<([^i])", "<i\\1", utterance)
    utterance = _re2.sub(r" A([^aui])", r" \1", utterance)
    utterance = _re2.sub(r"^A([^aui])", r"\1", utterance)

    return utterance.split(" ")


def process_utterance(buckwalter_text: str) -> str:
    """Phonetise one Buckwalter-encoded utterance, mirroring mantoq's
    ``process_utterance`` interface: space-separated phones, words joined by
    ``" + "``, ``-``/``sil`` word markers rendered as the ``sil`` token."""
    words = _preprocess_utterance(buckwalter_text)
    out_words = []
    for word in words:
        if word in ("-", "sil"):
            out_words.append(["sil"])
            continue
        out_words.append(_process_word(word))
    return " + ".join(" ".join(w) for w in out_words)
