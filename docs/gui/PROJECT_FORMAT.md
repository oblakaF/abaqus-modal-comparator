# The analysis project file (`.mcproj`)

For reviewers and anyone reading a project outside the program. Code: `src/services/analysis_project.py` (the format and
its checks) and `src/new_gui/project_model.py` (what is saved and how it is shown).

## What a project is

A saved record of one shown analysis: the frequencies, tables, status and pictures, and the identity of the files they
came from. The ODB, the UNV/UFF and the extracted FE package are not copied into it. The real projects tried were 3.2 MB
(plate) and 4.3 MB (a sandwich with a 3.9 GB package); dense synthetic pictures reached about 14 MB.

Its content is a **saved snapshot**, not a current result. Opening one reads only the project file: Abaqus, the FE reader
and the comparator do not start, and no source file is hashed.

## Container

Schema `universal/analysis-project/v1`. One ZIP file with exactly these members; any other name is refused:

| Member | Content | Limit |
|---|---|---|
| `manifest.json` | `schema`, `members` (size and SHA-256 of every other member), `members_sha256` | 1 MiB |
| `project.json` | the document below, as strict JSON | 32 MiB |
| `images/fe_<mode>.png`, `images/exp_<record>.png` | one saved picture per mode and record | 8 MiB each, 8000 px per side, 64 pictures |

The whole file is limited to 256 MiB. A file with another schema is refused by name, not guessed at.

## `project.json`

| Field | Holds |
|---|---|
| `schema`, `program` | format and program name |
| `saved_at` | when the results were saved; kept when the project is saved again |
| `written_at` | when this file was written |
| `scope` | the requested mode range (`first_mode`, `last_mode`, `mode_limit`) |
| `sources.fe_odb` | path, size, SHA-256 of the ODB, as recorded with the extracted modes that were read |
| `sources.fe_package` | manifest path, size and SHA-256, package SHA-256, the file list with sizes and hashes |
| `sources.experimental` | selected path, path read, size, SHA-256 taken when it was read |
| `sources.*.relocated_from` | earlier paths of a file later found moved with the same content |
| `modal_set` | the chosen set's position, key, names, record counts and whether it holds provisional records, and all sets of the file |
| `modes` | FE and experimental mode numbers and full-precision frequencies |
| `result` | status, statement, the FE, experimental and nearest-frequency tables, first elastic mode, rigid modes, notes, the registration reason and outcome |
| `comparison` | `null` unless a comparison was computed; otherwise pairs and errors, the MAC table as shown (`mac_cells`) and as numbers (`mac_values`, `null` where not finite), candidates, unmatched modes, warnings, provenance and gates |
| `registration` | `kind` (`NONE`, `ARCHIVED_REGISTRATION`, `USER_CONFIRMED_REGISTRATION`), confirmation and draft paths, who confirmed and when, evidence location, the content hashes, the limits |
| `shapes` | the component (`magnitude`), and per mode or record: number, label, picture, caption, or the service's refusal |

Hashes describe the data at the time it was read. A later hash is never recorded as if it described that data.

## Checks when reading

Nothing in a project is unpickled, executed or extracted to disk; `pickle` is not used anywhere in this format.

- ZIP structure and CRC, no encrypted or unusually compressed member, no repeated or unknown name.
- Every limit above, checked on the declared size and again on the bytes read.
- `manifest.json` matches its own hash, and every member matches its listed size and SHA-256.
- JSON with no repeated key, NaN or infinity; every field present, of the right type, none unknown.
- Pictures have a PNG header and a bounded size.
- The status must fit what the file holds: `REGISTRATION_REQUIRED` only without a comparison and registration,
  `USER_CONFIRMED_COMPARISON` only with a user-confirmed registration, `VERIFIED_COMPARISON` only with an archived one.

**These checks are not a signature.** They find damage and careless edits. Someone who rewrites a file with consistent
content and hashes is not detected, so a project is never evidence of anything. The file carries a statement of what the
program showed, not proof.

## Writing

The file is written to a temporary name beside the target, flushed, read back with the same checks and only then moved
into place. A failed or cancelled save leaves an existing project untouched and no temporary file. A project cannot
overwrite a source file of its own analysis.

## Status and revalidation

A status in a project is never raised, and its badge is never the green one used for a verified result.

| Step | What happens | What it does not do |
|---|---|---|
| Open Project | Shows the saved results. Reports only missing files and different sizes. | Hash sources; unlock Analyze. |
| Check source files | Hashes the ODB, experimental file and FE package now, and reports `UNCHANGED`, `MOVED`, `CHANGED`, `MISSING` or `UNREADABLE`. | Change the results or the status. The registration stays `NOT_REVALIDATED`. |
| Analyze, once the ODB and experimental file have the saved content | A fresh analysis through the ordinary services, on the saved modal set. Reuses the extracted package when found. | Reuse a saved status, pair or MAC. Start Abaqus without the usual consent. |
| Open confirmation, Compare | A saved confirmation is revalidated in full against the fresh data. | Happen by itself. |

Opening a project and checking its sources look at the paths the project names, reading them only to compare hashes. Open
projects only from people you trust: a path on a network share is contacted.

Missing or changed sources leave the snapshot readable and Analyze blocked. A moved file is accepted only when its content
hash equals the saved one; Save then records the new path and keeps the old one in `relocated_from`.
