# WORKING-DRAFT-R1: the workflow behind RUN_NEW_GUI.cmd

For reviewers of the working draft: what changed, and what the visible Windows run did and did not show.

## Code changes

- **RC6-F2 integrated.** Large FE read caches go only to a folder the user chose.
- **Wider extractions are reused.** An existing package of the same ODB content whose requested range covers modes 1-20
  no longer asks for Abaqus. The exact range is preferred; a narrower or later range is not reused.
- **Measured part and side (registration).** On a real sandwich the earlier code mapped 128 of 289 points to core nodes,
  because the 3 % geometry tolerance (18.7 mm there) exceeds the skin separation (2.85 mm). Now several FE instances need
  the measured instance stated, otherwise `REGISTRATION_REQUIRED`. A thin structure, whose depth along the measured side
  is within the tolerance, offers only the half of the depth towards the stated side. On the same files, all 289 points
  now lie on the top skin. Draft schema is now `universal/registration-draft/v2`; v1 drafts are refused.
- **Small corrections.** Record count no longer repeated in the modal set list; launcher wording.

No scientific threshold, historical registration or Auto-ID rule changed. The new thin-structure rule selects candidate
nodes from the stated side. It is a diagnostic rule, not an approved scientific gate.

## How the visible run was done

`RUN_NEW_GUI.cmd` started the real program in its own visible window with `.venv` (Python 3.14, PySide6 6.12), and an
external script drove it through Windows UI Automation and native file dialogs. A person did not click. Pictures are of
the program's windows only.

## Stages

| Stage | Plate (real) | Sandwich (real) | Beam (synthetic) |
|---|---|---|---|
| Launcher starts and ends with the window | PASS | PASS | PASS |
| File selection, paths with spaces | PASS | PASS | PASS |
| ODB package discovery, no Abaqus | PASS (real record) | PASS (**harness record**) | PASS (**harness record**) |
| UNV import | PASS | PASS | PASS |
| UFF import | PASS (same content renamed) | NOT_RUN | NOT_RUN |
| Modal-set selection | not needed | PASS | not needed |
| Frequencies, nearest table, shapes | PASS | PASS | PASS |
| `REGISTRATION_REQUIRED` without evidence | PASS | PASS | PASS |
| Registration, draft, confirmation dialogs | PASS (**stand-in evidence**) | PASS (**stand-in evidence**) | PASS (**stand-in evidence**) |
| Pairs, MAC, errors, pair shapes | PASS (**not scientific**) | PASS (**not scientific**) | PASS (synthetic) |
| Reopen a confirmation, used only on command | PASS | NOT_RUN | NOT_RUN |
| Changed file stops the comparison | PASS | NOT_RUN | NOT_RUN |
| FRF peak file refused for a comparison | PASS | NOT_RUN | NOT_RUN |
| Accepted archived registration still applies | not applicable | PASS (`VERIFIED_COMPARISON`) | not applicable |
| New extraction with Abaqus | NOT_RUN | NOT_RUN | NOT_RUN |

The real plate package carries the record of an earlier real extraction of the same ODB, so that discovery is not mocked.

**No registration here is physically verified.** No independent landmarks were available, so the stand-in evidence is one
central point labelled `SMOKE TEST ONLY: not physical evidence`. The stages show that the software runs; their pairs and
MAC values have no scientific meaning.

## Sizes seen

The sandwich (1.59 million nodes, 3.9 GB package, 30 modes): reading took about 5 minutes and about 7-8 GB of memory, and
a comparison about 90 seconds. The window stayed responsive.

## Tk scrolling failure

`test_real_tk_scrolling_keeps_every_column_accessible` failed once in a full run (`xview` right edge 0.9944, not 1.0). It
did not fail in 12 runs on the branch and its base, 15 more idle, and 6 with all 24 cores busy. `src/app.py`, which owns
that table, is unchanged since `main`. No regression is shown, so no Tk code changed. The likely cause, a layout not
settled after one `update()`, is not proven.
