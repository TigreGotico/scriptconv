"""Which letters spell which phoneme.

Every phoneme of a pronunciation is given a run of zero to four letters of the
word, in order, so that the runs spell the word: "thought" TH AO T becomes
th|ough|t and "box" B AA K S becomes b|o|x|(nothing). The pronunciation rules
need this to tell an unstressed vowel written "i" from one written "a".

The table of how likely each (phoneme, letters) pair is comes from CMUdict
alone, by expectation-maximisation over all its entries (``train``). The same
table aligns dictionary entries when the lexicon is built and the output of the
unknown-word model at run time (``Aligner.align``).
"""

from collections import defaultdict
import math

MAX_RUN = 4
_LENGTH_PRIOR = (0.02, 1.0, 0.3, 0.05, 0.01)      # starting belief by number of letters
_UNSEEN = -14.0


def base(symbol):
    """ARPABET symbol without its stress digit."""
    return symbol.rstrip("012")


def _expected_counts(word, phones, probability):
    letters, count = len(word), len(phones)
    forward = [[0.0] * (letters + 1) for _ in range(count + 1)]
    forward[0][0] = 1.0
    for j in range(1, count + 1):
        phone, previous, row = phones[j - 1], forward[j - 1], forward[j]
        for i in range(letters + 1):
            total = 0.0
            for k in range(min(MAX_RUN, i) + 1):
                if previous[i - k]:
                    total += previous[i - k] * probability(phone, word[i - k:i])
            row[i] = total
    evidence = forward[count][letters]
    if evidence <= 0.0:
        return None
    backward = [[0.0] * (letters + 1) for _ in range(count + 1)]
    backward[count][letters] = 1.0
    for j in range(count - 1, -1, -1):
        phone, following, row = phones[j], backward[j + 1], backward[j]
        for i in range(letters + 1):
            total = 0.0
            for k in range(min(MAX_RUN, letters - i) + 1):
                if following[i + k]:
                    total += following[i + k] * probability(phone, word[i:i + k])
            row[i] = total
    counts = {}
    for j in range(count):
        phone = phones[j]
        for i in range(letters + 1):
            if not forward[j][i]:
                continue
            for k in range(min(MAX_RUN, letters - i) + 1):
                if backward[j + 1][i + k]:
                    run = word[i:i + k]
                    weight = forward[j][i] * probability(phone, run) * backward[j + 1][i + k] / evidence
                    if weight > 1e-12:
                        counts[(phone, run)] = counts.get((phone, run), 0.0) + weight
    return counts


def _expectation(job):
    entries, table = job
    if table is None:
        probability = lambda phone, run: _LENGTH_PRIOR[len(run)]
    else:
        probability = lambda phone, run: table.get((phone, run), 0.0) + 1e-9 * _LENGTH_PRIOR[len(run)]
    totals, failed = defaultdict(float), 0
    for word, phones in entries:
        counts = _expected_counts(word, phones, probability)
        if counts is None:
            failed += 1
            continue
        for key, value in counts.items():
            totals[key] += value
    return dict(totals), failed


def train(entries, iterations=8, workers=1, log=None):
    """Estimate P(letters | phoneme) from ``(word, [phoneme, ...])`` pairs
    (phonemes without stress). Returns ``{phoneme: {letters: log probability}}``."""
    entries = [(word, [base(p) for p in phones]) for word, phones in entries
               if phones and len(word) <= MAX_RUN * len(phones)]
    table = None
    pool = None
    if workers > 1:
        import multiprocessing
        pool = multiprocessing.get_context("fork").Pool(workers)
    try:
        for iteration in range(iterations):
            shards = [entries[i::workers] for i in range(workers)]
            jobs = [(shard, table) for shard in shards]
            results = pool.map(_expectation, jobs) if pool else [_expectation(job) for job in jobs]
            totals, failed = defaultdict(float), 0
            for counts, misses in results:
                failed += misses
                for key, value in counts.items():
                    totals[key] += value
            mass = defaultdict(float)
            for (phone, _), value in totals.items():
                mass[phone] += value
            table = {key: value / mass[key[0]] for key, value in totals.items()}
            if log:
                log(f"alignment iteration {iteration + 1}/{iterations}: {len(table)} pairs, {failed} entries without a path")
    finally:
        if pool:
            pool.close()
    nested = defaultdict(dict)
    for (phone, run), value in table.items():
        if value >= 1e-6:
            nested[phone][run] = round(math.log(value), 3)
    return {phone: dict(sorted(runs.items())) for phone, runs in sorted(nested.items())}


class Aligner:
    def __init__(self, table):
        self.table = table

    def score(self, phone, run):
        known = self.table.get(phone)
        value = known.get(run) if known else None
        return value if value is not None else _UNSEEN - 2.0 * abs(len(run) - 1)

    def align(self, word, phones):
        """Split ``word`` into one run of letters per phoneme. ``phones`` may
        carry stress digits. Returns ``None`` when the word is too long for the
        pronunciation (an abbreviation such as "dept")."""
        phones = [base(p) for p in phones]
        letters, count = len(word), len(phones)
        if not count or letters > MAX_RUN * count:
            return None
        low = -1e18
        best = [[low] * (letters + 1) for _ in range(count + 1)]
        step = [[0] * (letters + 1) for _ in range(count + 1)]
        best[0][0] = 0.0
        for j in range(1, count + 1):
            phone, previous, row, trace = phones[j - 1], best[j - 1], best[j], step[j]
            for i in range(letters + 1):
                for k in range(min(MAX_RUN, i) + 1):
                    if previous[i - k] > low:
                        value = previous[i - k] + self.score(phone, word[i - k:i])
                        if value > row[i]:
                            row[i], trace[i] = value, k
        if best[count][letters] <= low:
            return None
        runs, i = [], letters
        for j in range(count, 0, -1):
            k = step[j][i]
            runs.append(word[i - k:i])
            i -= k
        return runs[::-1]
