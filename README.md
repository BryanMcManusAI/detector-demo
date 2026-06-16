# Bad-Data Detector — Method Demo (synthetic data only)

A small, self-contained, **runnable** demonstration of the method behind a rubric-annotation
quality detector. The point is to make the *method* verifiable by a stranger in one command —
not to ship the production system.

```bash
python3 detector_demo.py     # standard library only, no install, deterministic
```

## What it shows

1. **Substance over format.** A fabricated corpus of rubric annotations — some with genuine
   reasoning, some that follow the format and say nothing — is scored on transparent
   *substance* signals (lexical variety, hollow/tautological causality, buzzword density,
   tonal friction, a rescue for concrete task-specific references). Structural regularity is
   deliberately ignored, because annotation rubrics are templates by design.

2. **Disagreement-as-signal** (the core idea). A few vacuous items are deliberately mislabeled
   "lenient" — accepted as genuine — the same one-directional leniency a real calibration loop
   tends to surface. The detector never sees the labels; it just *disagrees* with some of them.
   Every planted label error lands in that small disagreement queue, which is far cheaper to
   re-read by hand than the whole corpus. Re-reading it sorts wrong labels from the detector's
   own misses — and audits your gold in the process.

## Gate a data batch in CI

`--gate` turns the detector into a **pass/fail check with a real exit code**, so it drops straight
into a data pipeline or pre-merge hook and *blocks a batch from training when too much of it is bad*:

```bash
python3 detector_demo.py --gate --max-bad-rate 0.20 --quiet
# exits 1 (fails the build) if the detector flags more than 20% of the batch as bad data
```

In GitHub Actions — no install, it's stdlib:

```yaml
# .github/workflows/dataquality-gate.yml
name: data-quality gate
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python3 detector_demo.py --gate --max-bad-rate 0.20 --quiet
```

Drop that file into `.github/workflows/` and it runs on every push (the synthetic batch is ~40% bad
by construction, so it clears a 0.50 ceiling but would fail a real 0.20 bar — point `--max-bad-rate`
at your own batch and threshold to gate real collection).

## What this is *not*

This is a **clean-room reconstruction from the publicly described approach.** It contains:

- **No proprietary code** — none of the production detector's source.
- **No internal or real data** — every annotation is fabricated in this file.
- **No production feature set or tuning** — the signals here are illustrative, chosen to be
  human-readable, not the real weighting.

The numbers it prints are synthetic. Their job is to show that the *architecture* — weight
substance, ignore format, treat label disagreements as hypotheses — separates real reasoning
from fluent emptiness, and that the disagreement set is where labeling errors hide.

Full write-up: **bryanmcmanus.ai/projects/bad-data-detector**
