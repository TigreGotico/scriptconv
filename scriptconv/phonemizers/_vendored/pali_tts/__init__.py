"""Vendored Pali grapheme-to-phoneme rules from dhammagift/pali-tts.

Source: https://github.com/dhammagift/pali-tts, file ``pali_ipa.py`` at commit
``a93830048ad1c606628331b4922694743dd1fdc8``, sha256
``0cbd81e0dec434622a4ec6899aedb618f3622249624dd0d5236a2962fec3b27c``. Licence
MIT. See ``LICENSE.md`` beside this file.

Pali (IAST) to IPA phonemes in the espeak-hi inventory that Piper hi_IN voices
were trained on. Pali spelling is phonemic, so this is a deterministic table:
no schwa deletion, every vowel is spoken.

The rules are unchanged, because a caller that drives those voices needs the
exact string upstream feeds them. Three parts of the upstream file are not
kept: ``export`` (it hands the tables to the upstream browser client),
``to_script`` with its ``DEVA_*`` tables (IAST to Indic script, which is not
phonemization), and the ``__main__`` self-test. The self-test assertions are
in ``tests/test_phonemizers_pali_tts.py``.
"""
import re
import unicodedata

VOWELS = {'a': 'ə', 'ā': 'aː', 'i': 'ɪ', 'ī': 'iː', 'u': 'ʊ', 'ū': 'uː', 'e': 'eː', 'o': 'oː'}
LONG = {'ā', 'ī', 'ū', 'e', 'o'}
CONS = {
    'kh': 'kʰ', 'gh': 'ɡʰ', 'ch': 'cʰ', 'jh': 'ɟʰ', 'ṭh': 'ʈʰ', 'ḍh': 'ɖʰ',
    'th': 'tʰ', 'dh': 'dʰ', 'ph': 'pʰ', 'bh': 'bʰ', 'ḷh': 'ɭʰ',
    'k': 'k', 'g': 'ɡ', 'c': 'c', 'j': 'ɟ', 'ṭ': 'ʈ', 'ḍ': 'ɖ', 't': 't', 'd': 'd', 'p': 'p', 'b': 'b',
    'ṅ': 'ŋ', 'ñ': 'ɲ', 'ṇ': 'ɳ', 'n': 'n', 'm': 'm',
    'y': 'j', 'r': 'ɾ', 'l': 'l', 'ḷ': 'ɭ', 'v': 'ʋ', 's': 's', 'h': 'h',
}
# Niggahita takes the place of articulation of the following stop.
NASAL_BEFORE = {'k': 'ŋ', 'g': 'ŋ', 'c': 'ɲ', 'j': 'ɲ', 'ṭ': 'ɳ', 'ḍ': 'ɳ', 't': 'n', 'd': 'n', 'p': 'm', 'b': 'm'}
TOKEN = re.compile('|'.join(sorted(CONS, key=len, reverse=True)) + '|ṃ|[aāiīuūeo]')
# Per-voice-language overrides: each Piper voice only knows the symbols its espeak language emits.
# 'A' = full short a.
PROFILES = {
    'hi': {}, 'mr': {}, 'ur': {'r': 'r'},
    'ne': {'u': 'u'},
    'ml': {'A': 'ɐ', 'i': 'i', 'u': 'u'},
    'te': {'A': 'a', 'i': 'i', 'u': 'u', 'r': 'r'},
}
PEYYALA = re.compile(r'(?:…|\.\.\.)\s*p[ae]\s*(?:…|\.\.\.)')
PUNCT = {',': ',', ';': ',', ':': ',', '—': ',', '–': ',', '.': '.', '?': '?', '!': '!'}
WORDS = re.compile(r"[a-zāīūṭḍṅñṇḷṃ]+|[,;:.?!—–]")


def normalize(text):
    text = unicodedata.normalize('NFC', text.lower())
    # "…pe…" / "…pa…" mark a passage left out: read as "peyyāla" (owner: without it only someone who knows
    # the text by heart can tell anything was skipped), set off by short pauses
    text = PEYYALA.sub(', peyyāla, ', text.replace('ṁ', 'ṃ').replace('ŋ', 'ṃ'))
    return text.replace('…', ', ')


def word_ipa(word, stress=True, full_a=False, final_m=False, lang='hi', heavy_back=True):
    prof = PROFILES[lang]
    full = prof.get('A', 'ʌ')
    toks = TOKEN.findall(word)
    out = []  # list of (kind, base_letter, ipa)
    for i, t in enumerate(toks):
        if t in VOWELS:
            out.append(['V', t, full if full_a and t == 'a' else prof.get(t, VOWELS[t])])
        elif t == 'ṃ':
            nxt = toks[i + 1][0] if i + 1 < len(toks) else ''
            out.append(['N', t, 'm' if final_m and not nxt else NASAL_BEFORE.get(nxt, 'ŋ')])
        else:
            out.append(['C', t, prof.get(t, CONS[t])])
    # e/o are short before a consonant cluster (metta, sotthi)
    for i, (k, b, _) in enumerate(out):
        if k == 'V' and b in 'eo' and i + 2 < len(out) and out[i + 1][0] in 'CN' and out[i + 2][0] in 'CN':
            out[i][2] = b
    # geminate aspirates: kkh -> k kʰ (already so), keep as is
    if stress:
        vidx = [i for i, x in enumerate(out) if x[0] == 'V']

        def heavy(vi):
            b = out[vi][1]
            after = 0
            j = vi + 1
            while j < len(out) and out[j][0] in 'CN':
                after += 1
                j += 1
            return b in LONG or after >= 2 or (vi + 1 < len(out) and out[vi + 1][0] == 'N')

        if len(vidx) >= 3:
            s = vidx[-2] if heavy(vidx[-2]) else vidx[-3]
            # heavy_back (round 14): a light antepenult yields to a heavy syllable right before it
            # (pītisukhaṁ -> PĪtisukhaṁ, not pīTIsukhaṁ "пи-ити"; vāRĀṇasī as in Hindi). Only the
            # neighbour: reaching further put it on BRAHmacariyaṁ, which the owner marked wrong.
            if heavy_back and len(vidx) >= 4 and not heavy(vidx[-2]) and not heavy(s) and heavy(vidx[-4]):
                s = vidx[-4]
        elif vidx:
            s = vidx[0]
        else:
            s = None
        if s is not None:
            if out[s][1] == 'a':
                out[s][2] = full
            out[s][2] = 'ˈ' + out[s][2]
    return ''.join(x[2] for x in out)


def to_ipa(text, stress=True, full_a=False, final_m=False, lang='hi', heavy_back=True):
    """full_a: short a as a full vowel everywhere instead of reduced ə (Hindi voices swallow ə).
    final_m: word-final niggahita as m (paṭhamam jhānam) instead of ŋ, which the voices tend to drop."""
    parts = []
    for m in WORDS.finditer(normalize(text)):
        tok = m.group()
        if tok in PUNCT:
            if parts and parts[-1] in PUNCT.values():
                continue
            parts.append(PUNCT[tok])
        else:
            parts.append(word_ipa(tok, stress, full_a, final_m, lang, heavy_back))
    s = ' '.join(parts)
    return re.sub(r' ([,.?!])', r'\1', s).strip(' ,')


# Piper hi_IN pratham, listening round 4: plain ɲ comes out as "n" (ñāṇa -> "nana"), ɲɲ as "n"
# (abhiññā -> "abhinā"), a word-final ŋ as a literal "n-g" (no sonorant ṁ reachable). These spellings won.
PRATHAM_RULES = [
    (re.compile(r'ɲɲ'), 'ɲːj'),  # round 5: ɲːj beat ɲː and nɲː
    (re.compile(r'(?<![ɲ])ɲ(?![ɲːjcɟ])'), 'ɲj'),
    (re.compile(r'ŋ(?=[ ,.?!]|$)'), 'ŋŋ'),  # round 8: ŋŋ is the velar ṁ (ङ) without the "-g" the voice adds to ŋ
    # (round 9's "open a" for an unstressed medial ʌ, added for viharati -> "viharti", is gone: round 22
    # found it behind most syllables swallowed since - jarāpi "japi", paṭhamaṁ, ponobbhavikā, taṇhāya)
    # round 12 (3 takes each): a single c between vowels still came out as "shch" 2 times of 3;
    # doubled cc was right every time
    (re.compile(r'(?<=[ʌaeoiuɪʊː])c(?=[ʌaeoiuɪʊːˈ])'), 'cc'),
    # round 36: the same for j (kāyasamphassajaṁ): doubled jj was ok in all 4 takes, single j bad in 1
    (re.compile(r'(?<=[ʌaeoiuɪʊː])ɟ(?=[ʌaeoiuɪʊːˈ])'), 'ɟɟ'),
    # round 18: y after a short vowel glided into it and its syllable was lost (passambhayaṁ ->
    # "пасамбхам"); doubled jj had no bad take of 8. Not after a long vowel or ɲː (ññ is ɲːj).
    # Only after a (rounds 25, 27): after i it hurt - dutiyaṁ, appaṭivattiyaṁ read better with one y.
    # Round 35: not before i (vedayitaṁ «ведайеиа»; a single y was ok in both takes)
    (re.compile(r'(?<=[ʌa])j(?=[ʌaeouʊˈ])'), 'jj'),
    # round 21: a word-initial ñ came out as "я" (Ñāṇañca -> "янанча"); n + j was the one that worked
    (re.compile(r'(?<![^ ,])ɲj'), 'nj'),
    # round 25: ñ before c as n (kiñci was right only as "kinci")
    (re.compile(r'ɲ(?=c)'), 'n'),
    # round 25: muhuttena - the h between two short u swallowed them; tense u held
    (re.compile(r'ʊhʊ'), 'uhu'),
    # round 33: samphassa from the aspirated pʰ came out as «сасфасса» (m lost, ph as f); p + h was ok in
    # both takes (round 34: j stays ɟ, dʒ and dʲ were bad everywhere). Not every ph: pharitvā with p + h bad, pʰ ok (round 56)
    (re.compile(r'mpʰ'), 'mph'),
    # round 24: viharati read "viharti" once the open-a rule was gone; an open a in the verb ending
    # -ati (word-final) brought it back, without the swallowing the general rule caused (round 22)
    (re.compile(r'ʌ(?=tɪ(?=[ ,.?!:;]|$))'), 'a'),
    # pratham has no word-final [ŋ] (Hindi has it only before k/g). Round 29: what Hindi itself does with
    # an anusvara won (6 best of 10) - दुक्खं dʊkkʰən, चक्खुं cʌkkʰũ; the explicit "ng" of rounds 24-26 was
    # heard as a literal «НГ». -iṁ stays "im" (paccaññāsiṁ; imasmiṁ was bad every way)
    (re.compile(r'[ʌa]ŋŋ(?=[ ,.?!:;]|$)'), 'ən'),
    # rounds 31-32: after h that ə came out as "e" (arahaṁ «арахем»); a full a there was ok in every take
    (re.compile(r'(?<=h)ən(?=[ ,.?!:;]|$)'), 'ʌn'),
    (re.compile(r'ʊŋŋ(?=[ ,.?!:;]|$)'), 'u\u0303'),  # u + combining tilde: the voice's map has no precomposed ũ
    (re.compile(r'(?<=ɪ)ŋŋ(?=[ ,.?!:;]|$)'), 'm'),
    # round 38: tiṇṇaṁ was bad as ɳɳən in both engines; a long ɳ won (best + ok), full a / dental nn did not
    (re.compile(r'ɳɳ(?=ən(?=[ ,.?!:;]|$))'), 'ɳː'),
    # rounds 38-39: the final -ha of Tasmātiha was not heard at all (hʌ, ha, ɦʌ, ɦaː); a long a won (best + ok)
    (re.compile(r'(?<=ɪ)hʌ(?=[ ,.?!:;]|$)'), 'haː'),
    # rounds 38-40: an unstressed word-final o inside a phrase was heard short next to a long ā (measured: ~110 ms
    # vs ~140 ms stressed ā). oːː, ˌoː, ˈoː, ɔːː, oːˑ (rounds 38-39) were all still short; a triple oː (~230 ms)
    # won in both phrases (best + ok). Only before the next word: phrase-final o is already long (~300 ms), and a
    # stressed one-syllable word (sˈoː, khˈoː) keeps its own o.
    (re.compile(r'(?<=[^ ,ˈˌ])oː(?= )'), 'oːoːoː'),
    # rounds 20, 41: ṭṭh came out as an affricate (sammādiṭṭhi «дичи», diṭṭhupādānaṁ «диччупадана»); a long ʈː
    # was the best spelling in both rounds (r20: 3 best 5 ok; r41: ok/ok, the only one with no bad take)
    (re.compile(r'ʈʈʰ'), 'ʈːʰ'),
    # round 41: the a after r in saṅkhāra- compounds was swallowed («санкхарпаччая»); a long aː won (best + ok)
    (re.compile(r'(?<=kʰaːɾ)ʌ(?=[^ ,.?!:;ˈʌaeoiuɪʊː])'), 'aː'),
    # round 42: pana before a comma read «пан» (now: ok/bad); an open a, aː and ʌː were all ok/ok - the open a, the
    # smallest change, for the word pana wherever it stands
    (re.compile(r'(?<![^ ,])pˈʌnʌ(?=[ ,.?!:;]|$)'), 'pˈʌna'),
    # round 43: aññena with ɲːj was bad in both takes, a single ɲj ok in both
    (re.compile(r'(?<![^ ,])ʌɲːjˈeːnʌ(?=[ ,.?!:;]|$)'), 'ʌɲjˈeːnʌ'),
    # round 43: byagghehi from bj was bad; jj (as after a, round 18) ok in both takes, so for a word-initial by-
    (re.compile(r'(?<![^ ,])bj(?=ˈ?[ʌa])'), 'bjj'),
    # round 46: the word jarā read «джа»; stress on rā (round 20's best) ok in all 4 takes, as it was 2 of 4
    (re.compile(r'(?<![^ ,])ɟˈʌɾaː(?=[ ,.?!:;]|$)'), 'ɟʌɾˈaː'),
    # round 46: kattha cut at the end; a long final aː ok in 3 of 4 takes (open a 1, ʌː 2, as it was 0)
    (re.compile(r'(?<![^ ,])kˈʌttʰʌ(?=[ ,.?!:;]|$)'), 'kˈʌttʰaː'),
    # round 51: mama with its final ʌ swallowed (bad both takes); an open a best + ok, as pana (round 42)
    (re.compile(r'(?<![^ ,])mˈʌmʌ(?=[ ,.?!:;]|$)'), 'mˈʌma'),
    # rounds 50, 52: dhārayāmīti «дхареямити» - the short a before y melts into e (Hindi ay); an open a with one j best + ok
    (re.compile(r'(?<=ɾ)ʌjj(?=aː)'), 'aj'),  # only after r: paccayā (round 41) keeps ʌjj
    # round 59: gayāyaṁ, gayāsīse «гее» (all 4 takes); the same open a with one j: «гай-» in 8 of 8 takes by the phoneme
    # recogniser (as it is 0 of 8). Where yā is not stressed (gayākassapo, owner: still «гее») the open a keeps jj and
    # yā gets a stress of its own: «гай-я» in 5 of 5 (with one j 2 of 3)
    (re.compile(r'(?<=ɡ)ʌjj(?=ˈaː)'), 'aj'),
    (re.compile(r'(?<=ɡ)ʌjj(?=aː)'), 'ajjˈ'),
    # round 52: pucchāmi «паччхами» - its u heard as a; a long uː best + ok (tense u and the current bad in both takes)
    (re.compile(r'pʊccʰ'), 'puːccʰ'),
    # round 53: bhikkhusammutiyā «самматья», the i before yā lost; jj ok in both takes (tense u, i and the current: bad)
    (re.compile(r'(?<=mmʊtɪ)j(?=aː)'), 'jj'),
    # round 51: uposathassa etāni ran together (bad both takes); the open a before the e: ok in both (a pause: best + ok,
    # but a pause inside a phrase is what round 45 threw out for So)
    (re.compile(r'ʌ(?= ˈ?eː)'), 'a'),
    # rounds 46-47: phoṭṭhabba with pʰ read «фо» (0 of 2); p + separate h ok 2 of 4 - better, owner: still not right
    (re.compile(r'pʰ(?=ˈ?oʈːʰ)'), 'ph'),
    # round 47: gāminiyā read «гаминья» (as now ok 1 of 2); a doubled jj best + ok
    (re.compile(r'(?<=ɡˈaːmɪnɪ)j(?=aː)'), 'jj'),
    # round 57: vimucciṁsūti read «чиксути» (round 56: 0 of 3); ṁ as m ok (and with a single c), a pause or ti apart bad.
    # The same ending -ṁsūti (an aorist + ti: jāniṁsūti, samanumodiṁsūti): 36 times in the canon
    (re.compile(r'ŋ(?=sˈuːtɪ)'), 'm'),
    # rounds 46-47: paṭipadā read «пратипада» (ʈ between vowels as Hindi's flap); a doubled ʈʈ ok 5 of 6, as now 3 of 6
    (re.compile(r'(?<=pʌ)ʈ(?=ˈ?ɪpʌd)'), 'ʈʈ'),
]


# Round 17: a one-syllable word ending in a vowel before a word starting with one ("So evamāha") came out
# as "сори эвамаха" in one take of two; a short pause between them was right in both. A glottal stop lost
# everywhere, and longer words (āyasmā ānando) were fine as they are, so only this case.
MONO_HIATUS = re.compile(r'(?<![^ ,])([^ ,.?!ʌəaeoiuɪʊ]*ˈ?[ʌəaeoiuɪʊ]ː?) (?=ˈ?[ʌəaeoiuɪʊ])')


def tune(ipa, rules=PRATHAM_RULES):
    for rx, rep in rules:
        ipa = rx.sub(rep, ipa)
    # round 43: "So imameva" with that pause read So apart from its sentence (bad in both takes); So unstressed
    # and joined was ok in all 3. Owner: no pause at all, but the o must stay long - the triple oː of rounds 38-40.
    # Round 45: so before e as well (So evamāha: joined long So best/ok/ok/ok, round 17's pause bad 3 of 4)
    return MONO_HIATUS.sub(lambda m: 'soːoːoː ' if m.group(1) == 'sˈoː' else m.group(1) + ', ', ipa)
