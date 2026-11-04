# WORKING-DRAFT-R2: Save Project and Open Project

For reviewers of the working draft: what was added, and what the visible Windows run did and did not show. The file format
is in [PROJECT_FORMAT.md](PROJECT_FORMAT.md).

## What the user gets

- **Open Project, Save Project, Save Project As**: buttons at the top of the Analyze page and in the File menu, with Ctrl+O,
  Ctrl+S and Ctrl+Shift+S. Close Project is in the File menu and in the snapshot's own card.
- **Opening a project** shows the saved tables, status and shape pictures. It reads only the project file.
- **Check source files** hashes the ODB, the experimental file and the FE package now, on command only. Analyze stays
  blocked until the ODB and the experimental file have the saved content.
- **Analyze** after that is an ordinary fresh analysis. A saved confirmation is not picked up: it must be opened and is
  then revalidated in full.

## What is saved

The status, every table as shown, the MAC matrix as shown and as full-precision numbers, the pairs, the frequencies, the
warnings, the registration facts and references, source paths and hashes, the chosen modal set, and one magnitude picture
per mode and record. MAC and pairs exist in the file only if they were computed.

## Sizes and times from the visible run

| | Plate (real) | Sandwich SP-13 (real) | Beam (synthetic) |
|---|---|---|---|
| Source data | small | ODB 716 MB, package 3.9 GB, 1.59 million nodes | small |
| Fresh analysis | seconds | 416 s (read 307 s, comparison 107 s) | seconds |
| Save | 7.3 s | 20.6 s | 4.1 s |
| Project file | 3.2 MB | 4.3 MB | 1.1 MB |
| Reopen | 0.3 s | 0.3 s, 239 MB of memory after it | 0.3 s |
| Check source files | 0.3 s | 8.3 s | under 1 s |

Windows never marked the window not responding during these steps (0 of 594 samples while reading the sandwich, 0 of 39
while saving it).

## Stages of the visible run

| Stage | Plate (real) | Sandwich (real) | Beam (synthetic) |
|---|---|---|---|
| Save Project As through the native dialog | PASS | PASS | PASS |
| Close the program, start again, Open Project | PASS | PASS | PASS |
| Visible table cells identical after reopening | PASS | PASS | PASS |
| Saved pictures shown | PASS (panels listed; picture not captured) | PASS | PASS |
| Analyze blocked before Check source files | PASS | PASS | not observed |
| Check source files: `UNCHANGED`, Analyze unlocked | PASS | PASS | PASS |
| Source missing: view stays, Analyze blocked | PASS | NOT_RUN | NOT_RUN |
| Source moved: accepted by content (`MOVED`) | PASS | NOT_RUN | NOT_RUN |
| Source changed: view stays, Analyze blocked | PASS | NOT_RUN | NOT_RUN |
| Fresh analysis after the check | PASS | NOT_RUN | PASS |
| Corrupt project refused with a message | PASS | NOT_RUN | NOT_RUN |
| Abaqus started | no | no | no |

The plate and sandwich runs came before three small later corrections (the order of a check in Analyze, a fallback for the
ODB size, and the Save As shortcut); those have their own tests, and the beam run came after the first two.

An external script drove the real window started by `RUN_NEW_GUI.cmd`, through Windows UI Automation and native file
dialogs. A person did not click. The visible comparison covers cells on screen in each tab; every table cell, the full MAC
matrix and the pairs are compared in `tests/test_working_draft_r2_project.py`.

**Real and stand-in steps.** The plate's `USER_CONFIRMED_COMPARISON` uses a stand-in confirmation from the earlier review,
labelled `SMOKE TEST ONLY: not physical evidence`. Its pairs and MAC have no scientific meaning, and it shows only that a
saved status is kept. The sandwich's `VERIFIED_COMPARISON` comes from the archived registration in
`docs/registrations/SP13_physical_registration.json`, and is shown when reopened as saved, with the amber badge. The missing,
moved and changed files were copies of the plate's experimental file; no original was changed.

## Limits

- **A project is not evidence.** The hashes find damage, not deliberate rewriting. Nothing is signed.
- **Pictures are fixed.** One component (magnitude), not rotatable, each on its own coordinates. Other components need a
  fresh analysis.
- **A closed window does not ask.** Closing with an unsaved result gives no prompt.
- **Cancelling a fresh analysis started from a snapshot** leaves an empty page. Open the project again; its file is untouched.
- **Scope.** Only the shown modal set is saved. Choosing another set needs a fresh analysis.
- **Paths.** Opening looks at the paths the project names, including network paths.
- **Narrow windows.** Below about 700 px the three project buttons stack. At 560 px the page still scrolls sideways under
  the offscreen test font, as it did before this work.
- **Save time.** Saving draws every picture again from the data in memory, which takes seconds to tens of seconds.
