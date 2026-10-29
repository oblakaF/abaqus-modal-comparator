# NEW-GUI.5 — applicability check of an archived physical registration FE↔EXP (2026-10-29)

Branch `feature/new-gui5-registration-readiness` from `main` `957bbd8`. **Status: IN_PROGRESS — WIP checkpoint (2026-10-29), not reviewed and not accepted.** The targeted and full regressions, CI, the `RUN_NEW_GUI.cmd` smoke and the old-interface smoke are not done yet.

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

### Windows (2026-10-29)

Everything ran on the real Qt `windows` platform (Segoe UI, 150 % native) with an isolated LOCALAPPDATA, on the
verified read-only copies. Their SHA-256 was checked before and after. Real mouse and keyboard input was sent with
SendInput.

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

**Other Windows checks (not completed at this WIP checkpoint):**
- **`RUN_NEW_GUI.cmd`.** INCONCLUSIVE: the first run was aborted by a harness focus loss; a second run was not
  evaluated.
- **Old interface (`RUN_PROGRAM.cmd`).** NOT_RUN.

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
- **Wording of the limits.** The limits are the service's wording, written for its reuse in an analysis ("this
  ODB"). Here nothing is reused or applied.
