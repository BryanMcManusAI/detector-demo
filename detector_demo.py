#!/usr/bin/env python3
"""
Bad-Data Detector — public method demo (SYNTHETIC DATA ONLY)
============================================================

A self-contained, runnable demonstration of the *method* behind a rubric-annotation
quality detector: score the SUBSTANCE of a written annotation, not its format, and treat
every disagreement with the existing labels as a hypothesis to re-check rather than a
detector error.

This file is a CLEAN-ROOM reconstruction from the publicly described approach. It contains
NO proprietary code, NO internal data, and NO production feature set or tuning. Every
annotation below is fabricated for this demo. Standard library only — `python3 detector_demo.py`.

What it shows, end to end:
  1. A fabricated corpus of rubric annotations: some with genuine reasoning, some that
     follow the format but say nothing.
  2. A transparent substance-over-format scorer that separates them.
  3. The signature move: deliberately mislabel a few items "leniently," then show the
     detector's disagreements recover exactly those planted errors — the labels get
     audited by the model, not the other way around.
"""
from __future__ import annotations
import argparse
import random
import re
import statistics
import sys
from dataclasses import dataclass, field

RNG = random.Random(7)  # deterministic

# ──────────────────────────────────────────────────────────────────────────────
# 1. Synthetic corpus. Two kinds of rubric annotation, assembled with variation so
#    no two items are identical. The CRITERION is a made-up rubric question; the
#    annotation is the worker's written justification for a score.
# ──────────────────────────────────────────────────────────────────────────────

CRITERIA = [
    "Does the response correctly handle the empty-input edge case?",
    "Is the explanation's causal chain valid, or does it skip a step?",
    "Does the summary preserve the source's hedged claims, or overstate them?",
    "Are the code comments accurate to what the function actually does?",
    "Does the argument address the strongest counterpoint, or dodge it?",
]

# Genuine: specific observations, hedging/friction, real engagement, asides.
GENUINE_OPENERS = [
    "I checked this against the actual input and",
    "Walking through it line by line,",
    "My first read said pass, but on a second look",
    "This one's borderline — I think",
    "Honestly I went back and forth here, but",
]
GENUINE_OBSERVATIONS = [
    "the empty list returns None instead of [], which the rubric treats as a miss",
    "step three assumes the cache is warm and never says so — that's the gap",
    "it quietly drops the 'usually' from the source and asserts it flatly",
    "the comment says O(n) but the nested loop makes it O(n^2)",
    "the rebuttal restates the thesis louder rather than meeting the objection",
    "the off-by-one only shows up when the range is exactly length 1",
]
GENUINE_FRICTION = [
    "I could see an argument the other way, though.",
    "Not certain, but it reads wrong to me.",
    "Probably fine for the common case, just not this one.",
    "Both are concise anyway, so it's a close call.",
    "Could be a typo rather than a logic error — hard to tell.",
]

# Vacuous: rubric format, fluent prose, tautology, buzzwords, no actual observation.
VACUOUS_OPENERS = [
    "This response effectively demonstrates a comprehensive understanding of",
    "The annotation provides a thorough and well-structured treatment of",
    "Overall, this submission successfully addresses the key aspects of",
    "The response showcases a robust and nuanced engagement with",
    "This is a strong, high-quality answer that fully captures",
]
VACUOUS_MIDDLES = [
    "the core requirements of the task in a clear and effective manner",
    "the essential criteria through a logical and coherent approach",
    "the relevant considerations with appropriate depth and rigor",
    "the necessary components in a comprehensive and detailed way",
]
VACUOUS_TAUTOLOGIES = [
    "It is correct because it accurately addresses what is being asked.",
    "This works well since it effectively does what it is supposed to do.",
    "The reasoning is valid as it logically follows the required logic.",
    "It meets the criteria because it satisfies the relevant standards.",
]


@dataclass
class Item:
    id: int
    criterion: str
    text: str
    true_label: str            # GENUINE | VACUOUS  (ground truth for this demo)
    given_label: str = ""      # the label a "lenient" reviewer assigned
    score: float = 0.0
    predicted: str = ""
    fired: list = field(default_factory=list)


def make_genuine(i: int) -> Item:
    c = RNG.choice(CRITERIA)
    parts = [
        f"{RNG.choice(GENUINE_OPENERS)} {RNG.choice(GENUINE_OBSERVATIONS)}.",
        RNG.choice(GENUINE_FRICTION),
    ]
    if RNG.random() < 0.5:  # sometimes a second specific observation
        parts.insert(1, RNG.choice(GENUINE_OBSERVATIONS).capitalize() + ".")
    return Item(i, c, " ".join(parts), "GENUINE")


def make_vacuous(i: int) -> Item:
    c = RNG.choice(CRITERIA)
    parts = [
        f"{RNG.choice(VACUOUS_OPENERS)} {RNG.choice(VACUOUS_MIDDLES)}.",
        RNG.choice(VACUOUS_TAUTOLOGIES),
    ]
    if RNG.random() < 0.6:
        parts.append(f"{RNG.choice(VACUOUS_OPENERS)} {RNG.choice(VACUOUS_MIDDLES)}.")
    return Item(i, c, " ".join(parts), "VACUOUS")


# Hard cases — deliberately ambiguous, so the demo doesn't score a suspicious 1.000.
# A real instrument misses a few of these, and that's the honest picture.
def make_terse_genuine(i: int) -> Item:
    # a real observation, but clipped and unhedged → easy to mistake for vacuous
    return Item(i, RNG.choice(CRITERIA), RNG.choice(GENUINE_OBSERVATIONS).capitalize() + ".", "GENUINE")

def make_polished_vacuous(i: int) -> Item:
    # empty, but name-drops a concrete-sounding term → tempts the rescue rule
    decoy = RNG.choice(["the cache", "the empty case", "the loop", "step three"])
    return Item(i, RNG.choice(CRITERIA),
                f"{RNG.choice(VACUOUS_OPENERS)} {RNG.choice(VACUOUS_MIDDLES)}, including {decoy}. "
                f"{RNG.choice(VACUOUS_TAUTOLOGIES)}", "VACUOUS")


def build_corpus(n_genuine=22, n_vacuous=20) -> list[Item]:
    items = [make_genuine(i) for i in range(n_genuine)]
    items += [make_vacuous(i + n_genuine) for i in range(n_vacuous)]
    base = n_genuine + n_vacuous
    items += [make_terse_genuine(base + i) for i in range(4)]
    items += [make_polished_vacuous(base + 4 + i) for i in range(4)]
    RNG.shuffle(items)
    # the honest baseline: a perfectly-applied label equals the truth
    for it in items:
        it.given_label = it.true_label
    return items


# ──────────────────────────────────────────────────────────────────────────────
# 2. Substance-over-format scorer. Transparent, conceptual features — the point is
#    the *architecture* (weight substance, ignore structure), not a tuned recipe.
# ──────────────────────────────────────────────────────────────────────────────

HEDGES = re.compile(r"\b(i think|probably|not certain|hard to tell|could be|borderline|"
                    r"went back and forth|reads wrong|i could see)\b", re.I)
TAUTOLOGY = re.compile(r"\bbecause it (accurately|effectively|logically)|since it effectively|"
                       r"as it logically|because it satisfies\b", re.I)
BUZZ = re.compile(r"\b(comprehensive|robust|nuanced|thorough|effective(ly)?|coherent|"
                  r"well-structured|high-quality|appropriate|relevant|essential)\b", re.I)
SPECIFIC = re.compile(r"\b(O\(n|line|step \w+|empty|off-by-one|cache|None|\[\]|typo|range|loop)\b")


def lexical_variety(text: str) -> float:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return len(set(words)) / len(words) if words else 0.0


def score_item(it: Item) -> Item:
    """Return a risk score in [0,1]: higher = more likely vacuous. Each axis is a
    transparent, human-readable signal about substance — never about formatting."""
    text = it.text
    n_words = max(len(re.findall(r"[a-zA-Z']+", text)), 1)
    fired = []
    risk = 0.0

    # axis: lexical variety — genuine thought introduces new content words
    tv = lexical_variety(text)
    if tv < 0.72:
        risk += 0.30; fired.append(f"low lexical variety ({tv:.2f})")

    # axis: tautology / hollow causality — "correct because it is correct"
    if TAUTOLOGY.search(text):
        risk += 0.35; fired.append("tautological causality")

    # axis: buzzword density without specifics
    buzz = len(BUZZ.findall(text)) / n_words
    if buzz > 0.06:
        risk += 0.25; fired.append(f"buzzword density ({buzz:.2f}/word)")

    # axis: tonal friction — genuine reasoning hedges and reveals its path
    if not HEDGES.search(text):
        risk += 0.15; fired.append("no hedging / friction")

    # rescue: a concrete, task-specific observation is strong evidence of engagement
    if SPECIFIC.search(text):
        risk -= 0.30; fired.append("specific task reference (rescue)")

    it.score = max(0.0, min(1.0, risk))
    it.predicted = "VACUOUS" if it.score >= 0.5 else "GENUINE"
    it.fired = fired
    return it


# ──────────────────────────────────────────────────────────────────────────────
# 3. Metrics + the disagreement-as-signal demonstration.
# ──────────────────────────────────────────────────────────────────────────────

def prf1(items, truth_attr="true_label"):
    tp = sum(i.predicted == "VACUOUS" and getattr(i, truth_attr) == "VACUOUS" for i in items)
    fp = sum(i.predicted == "VACUOUS" and getattr(i, truth_attr) == "GENUINE" for i in items)
    fn = sum(i.predicted == "GENUINE" and getattr(i, truth_attr) == "VACUOUS" for i in items)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def _report(items):
    print("=" * 70)
    print("STEP 1 — Detector vs. clean labels (synthetic ground truth)")
    print("=" * 70)
    p, r, f1 = prf1(items, "true_label")
    print(f"  {len(items)} fabricated annotations  |  precision {p:.3f}  recall {r:.3f}  F1 {f1:.3f}")
    print("  (Synthetic numbers — they show the SUBSTANCE features separate the two classes.)\n")
    # a couple of examples, with what fired
    for kind in ("VACUOUS", "GENUINE"):
        ex = next(i for i in items if i.true_label == kind)
        print(f"  [{kind}] score {ex.score:.2f} → {ex.predicted}")
        print(f"     “{ex.text[:96]}{'…' if len(ex.text) > 96 else ''}”")
        print(f"     fired: {', '.join(ex.fired) or '—'}\n")

    print("=" * 70)
    print("STEP 2 — Disagreement-as-signal: plant lenient mislabels, watch them surface")
    print("=" * 70)
    # A lenient reviewer accepts some vacuous items as genuine. Plant 4 such errors.
    planted = [i for i in items if i.true_label == "VACUOUS"][:4]
    for it in planted:
        it.given_label = "GENUINE"   # the lenient (wrong) label
    print(f"  Planted {len(planted)} lenient mislabels (vacuous items marked GENUINE),")
    print("  the same one-directional leniency the real calibration loop found.\n")

    # The detector never sees the labels; it just disagrees with some of them.
    disagreements = [i for i in items if i.predicted != i.given_label]
    recovered = [i for i in disagreements if i in planted]
    print(f"  Detector disagreed with the labels on {len(disagreements)} item(s) — a small,")
    print("  cheap-to-re-read queue. Every planted lenient error surfaces here, alongside a few")
    print(f"  of the detector's own hard-case misses; one human pass sorts which is which:\n")
    for it in disagreements:
        tag = "← planted lenient label error" if it in planted else "← detector's own miss (re-read)"
        print(f"     id {it.id:>2}  label={it.given_label:<8} detector={it.predicted:<8} {tag}")
    print(f"\n  Recovered {len(recovered)}/{len(planted)} planted label errors. The lesson isn't"
          f"\n  that the detector is always right — it's that the disagreement set is where wrong"
          f"\n  labels hide, and re-reading it is far cheaper than re-reading the whole corpus.")

    # What F1 looks like if you (wrongly) trust the lenient labels as ground truth.
    p2, r2, _ = prf1(items, "given_label")
    print(f"\n  Scored against the LENIENT labels, precision looks worse ({p2:.3f}) — the"
          f"\n  classic trap: the model looks broken because the labels are wrong. Re-checking"
          f"\n  the {len(disagreements)} disagreements by hand is one cheap pass that audits the gold.")
    print("\nDone. Method only; synthetic data only; no proprietary detail.")


def main():
    ap = argparse.ArgumentParser(
        description="Bad-data detector method demo; optionally gate a data batch on its flagged bad-data rate.")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero if the flagged bad-data rate exceeds the bar (drops into a data-pipeline / CI gate)")
    ap.add_argument("--max-bad-rate", type=float, default=0.20,
                    help="gate: max share of a batch the detector may flag as bad before the build fails (default 0.20)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the narrative; print only the GATE verdict")
    args = ap.parse_args()

    items = build_corpus()
    for it in items:
        score_item(it)

    if not args.quiet:
        print(__doc__)
        _report(items)

    if args.gate:
        bad = sum(it.predicted == "VACUOUS" for it in items)
        rate = bad / len(items)
        if rate > args.max_bad_rate:
            print(f"\nGATE: FAIL — flagged bad-data rate {rate:.0%} > max {args.max_bad_rate:.0%}"
                  f"  → blocking the batch from training.")
            sys.exit(1)
        print(f"\nGATE: PASS — flagged bad-data rate {rate:.0%} ≤ max {args.max_bad_rate:.0%}.")
        sys.exit(0)


if __name__ == "__main__":
    main()
