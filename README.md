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
