# Stage 0 baseline snapshot

`stage0_baseline.json` is the frozen reference result ROADMAP.md's Stage 2
work is diffed against (see "Required implementation order" and each stage's
completion criteria in `ROADMAP.md`).

It was captured from a real local run: `Job-1.odb` (the Auxetic panel FE
model, modes 6-17) against the Polytec full-scan Auxetic UNV export, using
the actual production pipeline (`modal_core.compare_modal_datasets`, i.e.
the same `install_*` chain and `quality_control` gating `app.py` uses), not
a re-implementation. It is not a synthetic fixture: the raw `.odb`/`.unv`
files are real experimental data and are intentionally not committed to the
repository (see `.gitignore` and `experimental_data/README.md`) — only their
SHA-256 hashes and the numeric result are recorded here.

Regenerate it with:

```
python tools/generate_baseline_snapshot.py \
    --abaqus "E:/sumin/Job-1.odb" \
    --abaqus-cache modal_comparator_output/analysis_31820a8085217a96/abaqus \
    --experiment "E:/sumin/500by500_Glue420_Auxetic_full_scan_260624.unv" \
    --start-mode 6 --end-mode 17 \
    --commit <git-rev-parse-HEAD> \
    --output docs/baseline/stage0_baseline.json
```

`--abaqus-cache` must point at a cache directory whose `extraction_signature.json`
still matches the `.odb` file's current size/mtime, or the script will try to
invoke Abaqus itself to re-extract.

Only regenerate this file when a numerical change to the accepted reference
result is intentional and reviewed — an unexpected diff against this file is
a regression, not routine drift.
