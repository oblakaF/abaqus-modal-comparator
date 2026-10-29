# NEW-GUI.5 — applicability check of an archived physical registration FE↔EXP (2026-10-29)

Branch `feature/new-gui5-registration-readiness` from `main` `957bbd8`. **Status: REVIEW_READY (2026-10-29), not
accepted.** The WIP checkpoint `3582bea` was completed without a code change: the checks below found no defect.

The Analysis page of the new interface gets a separate section, **Archived physical registration — applicability
check**. On the user's explicit command, **Check reference registration**, it checks with the existing service
whether an accepted archived physical registration (SP-02, SP-13) applies exactly to the FE results and the
experimental modal set already read. It is a preparation for a later, physically founded comparison.

**The registration is not applied in this stage.**
- No MAC is computed.
- No mode pair, node correspondence or orientation is made.
- Modal identity is not established.
- Nothing is saved as accepted for the user's workspace.

## Scientific service

- **The existing function.** `services.new_odb_comparison.bind_registration_by_fe_geometry(experimental_path, abaqus,
  experimental_dataset, cancel=...)`, unchanged.
- **Arguments.** It receives the data Inspect file already read:
  - `ExperimentalPreview.source_path`: the file the importer actually read; for an LMS project, its UNV / UFF
    companion;
  - `FePreview.dataset`;
  - `ExperimentalPreview.sets[set_index].dataset`.
- **No checks of its own.** The GUI reads nothing again and checks no coordinate, node, rotation, hash or tolerance.
- **What the service checks:**
  - the experimental file's fresh SHA-256 and size against the accepted PolyMAX sources;
  - the FE geometry identity;
  - the modal set's replay of the frozen registration;
  - the sealed registration's content compatibility and the presence of the mapped FE nodes.
- **Its outcome.** A verified registration, or a refusal with its reason.

## What the user sees

1. **One set choice.**
   - The check uses the modal set chosen for the frequency diagnostic (NEW-GUI.4); there is no second choice.
   - The section repeats the chosen set ("Modal set: Modal set i of n: ..." or "No modal set chosen above.").
2. **Nothing runs by itself.**
   - Before a click the badge reads **Not checked**.
   - The button is disabled, with the reason shown under it, until both files are read and a set is chosen.
3. **Verified** ("Archived reference verified"). The service's result is shown:
   - specimen and fixture (for example "SP02 — SP02/bravo-1-physical");
   - the modal set chosen and the archived modal set;
   - the FE geometry identity (SHA-256, node count);
   - the experimental source (path, SHA-256, size, archived source name);
   - the frozen registration (hash and file);
   - the service's checks and limits;
   - the warning, always shown: **"Verified archived reference for these selected data only. Registration not
     applied. Modal identity and MAC not established."**
4. **Not confirmed.**
   - The service's refusal is shown ("Not confirmed by the service: ...").
   - The note: "No archived registration applies to these data. This does not mean that your experiment is
     physically wrong, and the frequency diagnostic above remains available."
5. **Dataset 58.** For FRF peak records the section shows **PROVISIONAL — NOT A VALIDATED FITTED MODE** in red.
6. **Unchanged.**
   - The frequency diagnostic stays FREQUENCY_ONLY_DIAGNOSTIC with MAC NOT_COMPUTED, whatever the check says.
   - The NEW-GUI.3 shape panels, the Status page and the old interface.

## Background work and state

- **Off the GUI thread.** The check runs in a worker thread (`new_gui.registration_check_model.run_check`). Its
  outcome comes back through a queued signal.
- **Stale results never shown.**
  - The result is bound to the read FE and experimental previews (by identity) and to the set.
  - A replaced or cleared file, Inspect again, another set or a closed window cancels the request and discards its
    outcome (`RegistrationSlot`).
- **One heavy service at a time.**
  - The check and the frequency diagnostic share one lock (`registration_check_model.SERVICE_LOCK`, which is the
    diagnostic's lock), so they never run in parallel on a large FE model.
  - A request cancelled while it waits never calls the service.
  - The service is not interruptible midway, apart from its own cancellation while it hashes the file. A late
    cancellation discards its outcome.

## Architecture

| File | Role |
|---|---|
| `src/new_gui/registration_check_model.py` (new, no Qt) | `check` (the service on the read data), `run_check` (outcome: verified, refusal, error or cancelled; shared lock), `registration_view` (the service's result worded for display), `RegistrationSlot`. |
| `src/new_gui/registration_check_panel.py` (new) | `RegistrationCheckPanel`: the inputs used, Check reference registration, the verified registration or the refusal. |
| `src/new_gui/window.py` | The panel below the frequency diagnostic; it follows the diagnostic's set choice and the read previews; `busy()`, `wait_for_reads` and closing include it; About text. |
| `src/new_gui/__init__.py` | Stage "NEW-GUI.5 preview". |

`diagnostic_panel.py` and every scientific service, criterion, registration, SPEC, DECISIONS entry, M8 / D-077 record
and frozen evidence are unchanged.

## Checks

### Tests

- **`tests/test_new_gui5_registration.py`** (13 tests, no Qt). They use the project's synthetic fixture world (G2c /
  G2d-1 `World`) as the repository the service reads.
  - **Verified.** The exact accepted source, set and FE geometry are verified by the service. It receives the
    importer's file and the same dataset objects, and every shown value is the service's.
  - **LMS project.** It is checked with its companion file.
  - **Refused, with the service's reason:**
    - another FE geometry (moved, rescaled);
    - changed experimental bytes;
    - another modal set of the same file (the sets are never mixed).
  - **Never called:** MAC, comparison or pairing, geometric alignment, frozen-registration geometry, the frequency
    diagnostic, the sensitivity evidence check, the research archive, a second import or a process.
  - **Nothing written** in the world's records.
  - **Requests:**
    - no check without both reads and a set;
    - cancellation before, during and by the service;
    - an error is a message, not a refusal;
    - the lock is shared with the frequency diagnostic, and a request cancelled while it waits never runs;
    - only the current request is shown.
  - **On import** the model loads no service.
- **`tests/test_new_gui5_qt.py`** (12 tests, Qt offscreen):
  - **Before a click.** "Not checked"; disabled with the reason; the one shared set choice; nothing runs by itself.
  - **Verified.** The accepted set with the warning, the fields, the checks and the limits. A later frequency
    diagnostic is still frequency only with MAC NOT_COMPUTED.
  - **Refused, with the note:** another set; another FE geometry; FRF data, which stay PROVISIONAL. The diagnostic
    and the shape panels keep working.
  - **Stale outcomes discarded:** another set, a replaced FE file, a cleared experimental file, Inspect again, a
    closed window.
  - **One heavy service at a time.** The diagnostic waits for a running check.
  - **Layout.** The result adds no width.
- **`tests/test_new_gui1_qt.py`** (authorised adaptation). The Analysis page has exactly two commands, Run frequency
  diagnostic and Check reference registration, both disabled at an empty start; the test's name, comment and the
  module's introduction say so.
- **`tests/test_new_gui1_workspace.py`.** The allowed files of `src/new_gui` include the two new modules. They need
  no new project import.

**Runs (2026-10-29), with an isolated LOCALAPPDATA:**
- targeted (NEW-GUI.1–5, `test_new_odb_comparison`, importers, previews, shape views): 270 tests, OK, 3 skipped
  (the glyph test on `offscreen`, which passed separately on the `windows` platform, and 2 tests of an unconfigured
  data store);
- the full suite: 2935 tests, OK, 97 skipped. `test_g2_eigfreq_precision` (16 tests) reads machine-local work data
  and was not run.

### The new fitted series of 2026-10-29 (`docs/experimental/new_exp_20261029`)

Read only, directly from the delivery (`D:\Snadwich\New  EXP results`, two spaces); SHA-256, size and modification
time were the same before and after every run.

| Series | File | Modal set | Read | Single shapes | Frequency diagnostic | Registration check |
|---|---|---|---|---|---|---|
| SP-13 ROTATED 28.10.2026 | `SP13_500by500_Glue420_Auxetic_ROTATED_Polytec_261028.unv` | `polymax_bravo`, 12 records | yes | records 1 and 7 drawn | FREQUENCY_ONLY_DIAGNOSTIC, MAC NOT_COMPUTED | Not confirmed: "the experimental file SHA-256 8abf951dba4b… (448211 bytes) is not the PolyMAX source of an accepted physical registration." |
| SP-10 ROTATED 29.10.2026 | `SP10_b_rotated_500by500_Glue420_Honeycomb_ROTATED_Polytec_261029.unv` | `polymax_bravo`, 12 records | yes | records 1 and 7 drawn | as above | Not confirmed (SHA-256 432adf963085…, same reason) |
| `PLATE-300x300x1mm` ROTATED 27.10.2026 | `300by300_plate_only_1mm_ROTATED_Polytec_261027.unv` | `Polymax_bravo`, 11 records | yes | records 1 and 6 drawn | as above | Not confirmed (SHA-256 76db80aed1b4…, same reason) |
| SP-13 ROTATED FRF (auxiliary) | `SP13_500by500_Glue420_Auxetic_ROTATED_261028.unv` | 23 FRF peak records | yes | drawn, PROVISIONAL | as above, PROVISIONAL | PROVISIONAL shown; Not confirmed |

- **The FE side.** The SP-13 FE package (24 modes, 1 585 637 nodes) was used with all four files. No FE package of
  SP-10 or of the plate exists, so with those files it only stands in for the interface's behaviour: no FE-EXP
  result is claimed for them.
- **No transfer by itself.** After Inspect file the check reads "Not checked"; replacing the experimental file
  removes the earlier result.
- **The refusals are the expected, correct outcome.** None of these files is the source of an accepted
  registration. The refusal note says that the experiment is not thereby wrong, and the frequency diagnostic stays
  available.
- **Nothing offered without a registration.** Every visible text on the Analysis page that mentions MAC or pairs
  is a negative statement ("MAC: NOT_COMPUTED", "Mode pairs: NONE …", "NOT a mode pair", "no MAC or mode
  pairing"). The page has exactly two commands, and neither proposes MAC or pairs.
- **Archived references, for contrast** (the model on the read data):
  - SP-02 set `bravo-1` is verified (`SP02/bravo-1-physical`); sets `bravo` and `processing` are refused.
  - SP-13 260910 a (`SP13_a_polymax.unv`), set `best`, is verified (`SP13/best-physical`); set `processing` is
    refused.

### Windows (2026-10-29)

Everything ran on the real Qt `windows` platform (Segoe UI, DPI 144, that is 150 %, device pixel ratio 1.5) with an
isolated LOCALAPPDATA. Inputs:
- the verified read-only copies, with their SHA-256 checked before and after;
- the new series, read only from the delivery.

Real mouse and keyboard input was sent with SendInput.

**In-process run (real input; completion read from the worker threads themselves):**
- **New series.** As in the table above, with real clicks on Inspect file, the set and record choices, Show shape,
  Check reference registration and Run frequency diagnostic. A cleared experimental file removes the refusal and
  disables the check.
- **FE shape.** SP-13 FE mode 13 (199.977 Hz) drawn on 1 585 637 nodes.
- **Stale read.** The SP-02 FE read was replaced by the SP-13 package while it ran. The old read's thread ended
  after 6 s, and its outcome was discarded (`discarded` + 1). The card stayed "Not read" for the new file.
- **Pending check cancelled.** The first diagnostic of a fresh read held the shared lock, and the check waited
  ("Checking..."). Each of these cancelled both:
  - the set reset to "Choose a modal set...";
  - Inspect again of the experimental file;
  - closing the window.

  Each time, after both threads had ended, `discarded` grew by 1 for the check and by 1 for the diagnostic, and
  nothing was shown.
- **Sizes.** 900 × 680 and 1366 × 768 in physical pixels, and the same sizes in logical pixels (1350 × 1020,
  2049 × 1152): no page-level horizontal scroll bar, the content fits, no missing glyph.

**`RUN_NEW_GUI.cmd` (native file dialogs; the window's state read through Windows UI Automation, that is the texts
and enabled states the program displays, never the cache):**
- **Start.** The window appeared after 7.5 s; empty start with both commands disabled and "Not checked".
- **Native dialogs.**
  - The SP-13 FE package (Ctrl+1) and the three new files (Ctrl+2) were chosen in the native dialog, including the
    path with two spaces.
  - A cancelled dialog changed nothing: the paths and the refusal stayed.
- **New series.** Each was read ("Content read; preview only"). The check showed "Not checked" until clicked, then
  "Not confirmed" with the service's SHA-256 reason and the note. The frequency diagnostic then gave
  FREQUENCY_ONLY_DIAGNOSTIC.
- **SP-02.**
  - Set 1 was verified ("Archived reference verified", the warning, `SP02 — SP02/bravo-1-physical`).
  - Switching to set 2 removed the result; set 2 was then refused with the pinned-set reason.
  - Diagnostic and check pending ("Checking..."), then set 2: "Not checked" at once and still 30 s later, with no
    result shown.
- **Sizes.** The four sizes above: no page-level horizontal scroll bar.
- **End.** The window was closed with a diagnostic and a check pending. `cmd` exit code 0; no child process and no
  `new_gui` process left; inputs unchanged.

**Old interface (`RUN_PROGRAM.cmd`).** The main window opened after 16 s and closed (one "Don't save" prompt);
`cmd` exit code 0, no child process.

**Earlier WIP run on the verified copies (`3582bea`):**
- **Empty start.** The two commands are disabled with the reasons; the check reads "Not checked".
- **SP-02 FE package + SP-02 UNV** (three dataset-55 sets).
  - **A stale result discarded.** Set 1 was chosen. Run frequency diagnostic was clicked, then Check reference
    registration, which waited for the diagnostic's lock. Set 2 was chosen while both were pending. Both outcomes were
    discarded and nothing was shown.
  - **Set 1, "Bravo (1)" (`bravo-1`): verified by the service in 2.3 s.**
    - SP02 — SP02/bravo-1-physical.
    - FE geometry `72e8597a…` (1 663 816 nodes).
    - Experimental source SHA-256 `2671db01…`.
    - Frozen registration `9b63f6c8…` (`docs/registrations/SP02_physical_registration.json`).
    - The service's four checks and four limits.
    - The warning "… Registration not applied. Modal identity and MAC not established."
    - A frequency diagnostic run afterwards stayed FREQUENCY_ONLY_DIAGNOSTIC with MAC NOT_COMPUTED.
  - **Set 2, "Bravo" (`bravo`).** Choosing it removed the result. After a click the service refused: "modal_set.name:
    selected 'bravo'; … pinned 'bravo-1'". The refusal note was shown.
- **SP-04 FE package + SP-04 UNV (dataset 58 only).**
  - PROVISIONAL was shown before the click.
  - The service refused: "the experimental file SHA-256 f7c46dad… is not the PolyMAX source of an accepted physical
    registration". This is correct, because no accepted registration exists for SP-04.
  - The frequency diagnostic still ran.
- **Sizes and pages.**
  - 1366 × 768 and 900 × 680: no page-level horizontal scroll bar and no missing glyph.
  - Status page unchanged.
- **End.** The window closed with nothing running. Inputs unchanged; no tracked file under `docs/registrations`,
  `docs/baseline` or `docs/auto_id` changed.

The WIP checkpoint's own `RUN_NEW_GUI.cmd` run was aborted and judged a read's end by the cache appearing; it is
not counted and was replaced by the run above.

## Not in this stage

- No registration applied, no MAC, mode pair, node correspondence or orientation.
- No orientation chosen by frequencies or MAC.
- No registration, catalogue, STATUS or frozen evidence changed.
- No Abaqus, solver, LM, Auto-ID or new FE computation.

## Limits

- **Archived references only.** Only the accepted archived registrations (SP-02 `bravo-1`, SP-13) can be verified.
  Any other experiment, set or FE geometry is refused, which says nothing about its physical correctness.
- **Not interruptible.** The service cannot be stopped midway, apart from its own cancellation while it hashes the
  experimental file. A late cancellation discards its outcome.
- **No FE package for SP-10 or the plate.** Their checks used the SP-13 FE package as a stand-in. Since the
  service refuses at the experimental file's identity first, that does not change the outcome. Their frequency
  diagnostics are interface checks only.
- **A cancelled request's end, seen from outside.** Through `RUN_NEW_GUI.cmd` the end of a cancelled worker cannot
  be observed: only the displayed state is checked ("Not checked", no result, 30 s later). This point is
  INCONCLUSIVE there, and it is covered by the in-process run, which waits for the threads themselves.
- **Wording of the limits.** The limits are the service's wording, written for its reuse in an analysis ("this
  ODB"). Here nothing is reused or applied.
