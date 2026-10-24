# APP-E2E.3 — preparation for repeat experiments (2026-10-25)

Branch `fix/app-e2e3-experiment-readiness` from `main` `5fc8f82` (after PR #95). It is a program change, not a
scientific stage.

It does three things:

- fixes P-2 and P-3 of APP-E2E.1;
- adds a person's diagnostic note `SETUP_UNDER_REVIEW` for experimental series that the test setup may have
  influenced, so repeat measurements (SP-13 and others) can be handled safely;
- records the plate suspension observation as information on the test conditions.

**Not run:** Abaqus, FE solves, LM and new experimental computations.

## P-2: FE rigid-body modes are separate diagnostic records

**Before.** The frequency-only diagnostic listed the near-zero rigid-body FE modes as ordinary FE modes. They were
also candidates for the nearest-frequency rows. The comparison path already excluded them.

**Now.** The diagnostic paths use the comparator's own criterion: the six-vector rigid-body subspace projection of
the mode shape, with residual ≤ 0.02 (`quality_control`). No frequency threshold is introduced. Under this criterion:

- the frequency-only diagnostic lists the rigid-body modes in their own section ("FE RIGID-BODY MODES", with the
  residual of each), and its nearest-frequency rows use the elastic FE modes only;
- the mode viewer keeps every FE mode viewable and labels the rigid-body ones "— rigid-body (diagnostic)";
- the diagnostic PDF / Excel has a Classification column. The FE range for the "below / above the FE range" notes is
  the elastic range.

**Nothing is removed.**

- The first elastic FE mode stays available.
- No experimental mode is excluded: experimental mode 1 is never dropped automatically.
- The criterion depends on the shape, not the frequency. A shape that is not a rigid-body motion stays elastic even at
  a near-zero frequency.

**Where it runs.** The classification is computed once in the analysis worker, never on the GUI thread. In the
comparison path the quality-control record is reused rather than recomputed.

## P-3: the 11. Scaling tab

**The causes:**

- The window-wide responsive wrap computed the width of a not yet shown tab as 1 px. That gave a 280 px text column,
  and the table was pushed out of view.
- The long label texts in the frame titles could not wrap.
- At 150 % (and at the minimum window size) the lower panes were squeezed and their controls cut off.

**The fix (no redesign):**

- labels wrap to the real width of their pane, and a tab gets its wrap recomputed when it is shown;
- the label texts moved from the frame titles into wrapped lines inside the frames (the frame titles keep their
  names);
- the tab scrolls vertically when the panes need more height than the window gives;
- the sashes never make a pane smaller than its content or its row of controls.

**Checked** in the real window at Tk scaling 1.33 and 2.0 (100 % and 150 %), at 1680 × 1000 and at the minimum window
size, after a comparison:

- every label shows all its lines;
- no button, spin box or unwrapped label is narrower than requested;
- nothing lies outside the scrollable content.

On the unfixed `main` the same check fails in all four cases.

## SETUP_UNDER_REVIEW (a person's note on an experimental series)

**In the GUI.** 1. Files > Series review shows the note of exactly the selected series. *Review series...* records or
withdraws it.

**Rules:**

- **Set by a person only, never automatically.** The reason, the source of the information and the experiment /
  test-run identifier are mandatory.
- **Bound to the series identity.** The identity is the SHA-256 and size of the experimental file content plus the
  modal set; the file name is informational only.
  - A renamed copy with the same content carries the same note.
  - A repeat measurement or a re-export with other content, or another modal set, is a new series: it has no note.
  - Having no note is stated explicitly as "not a statement that the series is valid".
- **Recorded append-only in a per-user log** (`~/.abaqus_simcenter_modal_comparator/experimental_series_review.json`,
  outside every data store). Setting and withdrawing are both kept, and the experimental files are only read
  (hashed).
- **Shown** in the Files tab and in the diagnostic PDF / Excel: the summary row "Experimental series review", a
  conclusion line, and the provenance.
- **A note only.** It changes no frequency, mode shape, MAC, pairing, criterion, accepted registration or scientific
  status.
  - It is not an analysis input, so the result stays active when it is set.
  - It is not a gate, and it is not an Auto-ID scheme.
  - SP-02, SP-13 and SP-08 are not declared unreliable.

## Plate suspension observation (M11 §21)

**The observation (owner).** With a changed suspension, the plate's first experimental resonance appeared near 19 Hz
instead of about 33 Hz; FE 7 is 19.07 Hz.

**How it is recorded.** As information on the test conditions only:

- it is not a proven correspondence of mode numbers;
- no experimental mode is excluded;
- the existing series stays as recorded;
- a repeat measurement is a new series.

The M11 statuses are unchanged.

## Verification

| Check | Environment | Result |
|---|---|---|
| `tests/test_app_e2e3_experiment_readiness.py` (P-2, P-3 at 100 % / 150 %, SETUP_UNDER_REVIEW, mode rules) | Windows, Python 3.14.6 | 14 passed (+5 subtests) |
| The same P-2 / P-3 tests on unfixed `main` `5fc8f82` | same | 8 failed, 1 passed (the one passing test does not depend on the fix) |
| Profile groups: P-2 / viewer / diagnostic report / P-1 / R7 / guided / G1 / G2c / G2d / UI workflow / SP-02 / SP-13 / material-ID UI | same | 317 passed, 15 skipped (store-gated) |
| Full `python -m unittest discover -s tests`, three consecutive runs | same | **2529 OK, 96 skipped** each |
| Full pytest | same | 2468 passed, 112 skipped, **0 failed** |
| `research/m11_r65` synthetic tests | same | 29 OK |
| Real launch `RUN_PROGRAM.cmd`, clean profile | Windows 10 | main window after 61 s, no traceback, closes with exit code 0; the Series review row is shown |
| SP-02 accepted comparison, real window (CORE-E2E copies, cached extraction, no process) | same | 20 / 20 PASS. Strict pairs R1–R3 reproduced (MAC within 1e-9); FE 6 shown as a rigid-body record; experimental mode 1 kept; all 11 tabs open |
| Plate without physical registration (R6 + V3), with the note | same | 29 / 29 PASS. R7-A unchanged; FE 3–6 rigid-body records, elastic from FE 7; nearest rows elastic only; experimental mode 1 (33.45 Hz) kept. The note was set in the dialog and shown; the outcome and its export stayed active; the diagnostic PDF / Excel state it; MAC NOT_COMPUTED |
| Damaged UNV, real window | same | 12 / 12 PASS. FE 3–6 rigid-body records; no hang |
| 11. Scaling, real window, Tk scaling 1.33 / 2.0, 1680 × 1000 / minimum | same | 4 / 4 PASS (fixed); 4 / 4 FAIL on `5fc8f82` |

**Found and fixed during verification:**

- **Series identification.** The first version posted the answer from the worker thread with `root.after`; that
  works only inside `mainloop`. It now uses the queue polling of the modal-set discovery.
- **The note text.** It ran under the *Review series...* button; it now wraps to its own column.
- **Test teardown.** A 150 % test left the Tk scaling changed for later tests, because Tk keeps it per display. The
  test now restores it.
- **Tcl_AsyncDelete.** A full unittest run aborted with "Tcl_AsyncDelete … wrong thread". Background threads of
  dialog tests held Tk objects past the test, which was a latent hazard of `test_guided_registration` that the new
  threads made visible. The test teardowns now join those threads and free the windows on the main thread. Three
  consecutive full runs are clean.

**Not run:** the store-gated real-data regressions (original stores).

## Limits

- **P-2** separates rigid-body modes by shape.
  - A mode without usable shape data has residual 1 and counts as elastic.
  - When an analysis failed before the classification was recorded, the FE list shows plain FE modes and the report
    says "not classified".
- **SETUP_UNDER_REVIEW** is per user (per machine profile). It is not shared through the repository and is not part
  of a project file.
- **The 150 % check** sets the Tk scaling; the Windows display setting itself was not changed.
- **Store-gated regressions** need the original stores and are `NOT_RUN`.
- **Unchanged:**
  - MAC, pairing, registration, QC criteria and thresholds, SPEC v1.2, Auto-ID and production gates, the pinned
    extractor;
  - M8 GATE `NOT_MET`; D-077 `NO_GLOBAL_PARAMETER_VALUE`; production Auto-ID BLOCKED / NOT_AUTHORISED.
