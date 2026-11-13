#!/usr/bin/env python3
"""How closely does scriptconv's ``Phonemizer.IQRA`` edge match IqraEval's
own ``phoneme_ref``? Score it against IqraEval/Iqra_train.

The gold is `IqraEval/Iqra_train <https://huggingface.co/datasets/IqraEval/Iqra_train>`_
(74k rows of Qur'anic and MSA sentences with a custom phoneme notation, built
for the IqraEval / Qur'an recitation-assessment shared task). Same convention
as TigreGotico/arbtok's ``scripts/benchmark_iqraeval.py``, which this script's
loader is copied from: only the parquet's *text* columns are ever read —
``load_gold`` opens the remote parquet with ``pyarrow`` + ``huggingface_hub``'s
``HfFileSystem`` and requests ``columns=[...]`` without ``audio``, so pyarrow's
column projection fetches HTTP byte-ranges for the requested columns only.
**No gold is vendored into this repo**; the cache directory
(``scripts/.cache_iqraeval``) is gitignored.

  ``tashkeel_sentence``   fully diacritized orthography — the IQRA edge's
                          input contract.
  ``phoneme_ref``         space-separated phoneme reference in Nawar Halabi's
                          Arabic-Phonetiser notation (Interspeech 2025,
                          doi:10.21437/Interspeech.2025-2411 — "we employed
                          the phonetizer introduced by Nawar Halabi").

``Phonemizer.IQRA`` (``scriptconv.phonemizers.ar.IqraPhonemizer``) is backed
by ``_vendored/iqra_phonetiser/phonetiser.py`` — a port of the IqraEval
shared task's OWN published data-prep code (Iqra-Eval/MSA_phonetiser's
``phonetiser/phonetise_Arabic.py``, confirmed to be what generates
``phoneme_ref`` itself), NOT mantoq's vendored copy of Nawar Halabi's
pristine original. Three deterministic, tajwid/grammar-cited text-level
transforms are applied before calling it (see its docstring and
``scriptconv/phonemizers/ar.py``'s ``_iqra_preprocess``): universal tanwin
elision, wāw al-jamāʿah's silent alif, and utterance-initial hamzat al-waṣl
on the definite article realized with fatḥa. This script measures exact
token-level agreement between the edge's ``Alphabet.HALABI`` output and
``phoneme_ref``.

As of the introducing PR: **98.3% exact token-match (2,544/2,588)** on the
dev split. Of the 44 residual mismatches, 37 (84%) share one mechanical,
dataset-generation-bug signature, not a phonetiser fidelity gap: the
organizers' own ``isFixedWord`` reduces a word to a "consonant skeleton" by
keeping only characters in the fixed set ``h*Ahn'>wl}kmyTtfdb`` (see
``phonetiser.py``'s ``isFixedWord``) and looks that skeleton up in a small
fixed-pronunciation table. Any word whose only letter in that set is a bare
wāw — e.g. "رَوْضَةً" (rawḍa, "garden"), "زَوْجَةٌ" (zawja, "wife"), "صُورَةٌ"
(ṣūra, "picture"), "عُقُوقِ" (ʿuqūq, "undutifulness"), "وَضْعَ" (waḍʿa,
"placement") — collapses to the skeleton ``"w"`` and gets replaced wholesale
by the fixed entry for "w a", regardless of the word's actual (and entirely
different) pronunciation. Two occurrences of the exact same word
("رَوْضَةً") in two different dev rows both show this identical collapse,
confirming it is a deterministic property of the generation pipeline, not
noise — see the introducing PR for the full row-level evidence. Excluding
these 37 rows, the edge is 2544/2551 = **99.73%** exact on the remainder of
the dev split — comfortably past the >99% bar for anything actually within
this edge's power to fix.

Usage
-----
    python scripts/benchmark_iqraeval.py                  # dev split, full
    python scripts/benchmark_iqraeval.py --split train --limit 5000
    python scripts/benchmark_iqraeval.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Dict, List, Tuple

# Prefer the repo this script lives in over any other installed/editable
# ``scriptconv`` (e.g. a different checkout/worktree earlier on sys.path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HF_REPO = "IqraEval/Iqra_train"
CACHE_DIR = os.environ.get(
    "IQRAEVAL_CACHE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache_iqraeval"),
)
TEXT_COLUMNS = ["id", "sentence", "tashkeel_sentence", "phoneme_ref"]


def _cache_path(split: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{split}.parquet")


def _remote_files(split: str) -> List[str]:
    from huggingface_hub import HfApi
    api = HfApi()
    info = api.dataset_info(HF_REPO)
    files = sorted(
        s.rfilename for s in info.siblings
        if s.rfilename.startswith(f"data/{split}-")
    )
    if not files:
        raise FileNotFoundError(f"no {split!r} parquet files in {HF_REPO}")
    return files


def load_gold(split: str, limit: int = 0) -> "list[dict]":
    """Text-only rows for *split* ('dev' or 'train'), pulled and cached once.

    Reads only ``TEXT_COLUMNS`` (never ``audio``) via pyarrow column
    projection over ``HfFileSystem`` — see the module docstring.
    """
    import pandas as pd

    cache = _cache_path(split if split == "dev" or not limit else f"{split}-{limit}")
    if os.path.exists(cache):
        df = pd.read_parquet(cache)
    else:
        import pyarrow.parquet as pq
        from huggingface_hub import HfFileSystem

        fs = HfFileSystem()
        frames = []
        rows_so_far = 0
        for fname in _remote_files(split):
            print(f"fetching columns {TEXT_COLUMNS} from {HF_REPO}/{fname} …",
                  file=sys.stderr)
            path = f"datasets/{HF_REPO}/{fname}"
            table = pq.read_table(path, filesystem=fs, columns=TEXT_COLUMNS)
            frames.append(table.to_pandas())
            rows_so_far += table.num_rows
            if limit and rows_so_far >= limit:
                break
        df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        df.to_parquet(cache)
    if limit:
        df = df.iloc[:limit]
    return df.to_dict(orient="records")


def score(rows: "list[dict]") -> Tuple[dict, "Counter", "list[dict]"]:
    """Exact token-match rate of ``Phonemizer.IQRA`` against ``phoneme_ref``,
    plus a Counter of the most common diff classes (difflib opcodes over the
    space-separated token lists) for residual-class reporting."""
    import difflib
    from scriptconv.phonemizers.registry import get_phonemizer
    from scriptconv.phonemizers.enums import Phonemizer, Alphabet

    engine = get_phonemizer(Phonemizer.IQRA, alphabet=Alphabet.HALABI)

    n = exact = 0
    opcount: Counter = Counter()
    mismatches = []
    for row in rows:
        try:
            pred = engine.phonemize_string(row["tashkeel_sentence"]).split()
        except Exception as exc:  # a crash is a data point, not a silent skip
            pred = [f"<<ERROR:{exc}>>"]
        gold = row["phoneme_ref"].split()
        n += 1
        if pred == gold:
            exact += 1
            continue
        mismatches.append({"id": row["id"], "text": row["tashkeel_sentence"],
                            "pred": " ".join(pred), "gold": " ".join(gold)})
        sm = difflib.SequenceMatcher(None, pred, gold)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            opcount[(tag, tuple(pred[i1:i2]), tuple(gold[j1:j2]))] += 1
    return {"n": n, "exact": exact, "rate": exact / max(n, 1)}, opcount, mismatches


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "train"], default="dev")
    ap.add_argument("--limit", type=int, default=0,
                    help="row cap (default: 0 = full dev; use for train, 71k rows)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = load_gold(args.split, limit=args.limit)
    print(f"{args.split}: {len(rows)} rows", file=sys.stderr)

    metrics, opcount, mismatches = score(rows)

    print("-" * 72)
    print(f"Phonemizer.IQRA on IqraEval/{args.split} (n={metrics['n']})")
    print(f"  exact token-match: {metrics['exact']}/{metrics['n']}  ({metrics['rate']:.4f})")
    print("-" * 72)
    print("Top 20 residual diff classes (tag, predicted, gold):")
    for key, c in opcount.most_common(20):
        print(f"  x{c}  {key}")

    if args.json:
        out = {
            "split": args.split,
            "metrics": metrics,
            "top_diffs": [[list(k), c] for k, c in opcount.most_common(50)],
            "mismatches_sample": mismatches[:100],
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"wrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
