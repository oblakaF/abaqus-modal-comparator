# Solver profiles (M4.6)

Schema `auto-id/solver-profile/v1`. The parser is `src/domain/identification_run.py`
(`load_solver_profile`); the launcher is `src/services/forward_solver.py`.

A solver profile is **separate data**, by SUPERVISOR decision (M4_DECISION_RECORD.md §6.1).
The Abaqus release, `cpus`, the command template and the scratch policy stay outside the
M3 forward-model manifests, which are unchanged.

| Field | Meaning |
|---|---|
| `forward_model_id`, `job_prefix` | The forward model the profile belongs to; must equal the M3 manifest |
| `abaqus_release`, `version_marker` | The release, which must appear in the job's `.dat` |
| `command_template` | Exactly `{abaqus} {job} {inp} {cpus} {scratch}`, no machine paths. The archived CARBON-4C/5A convention: `abq2024.bat job=… input=… cpus=…[ scratch=…] interactive ask_delete=OFF` |
| `cpus` | SP02 8, SP13 1 (archived) |
| `scratch` | `null`, or a store name whose root (`AUTO_ID_FIXTURE_ROOT_<STORE>`) is the solver scratch directory. SP02 uses the CARBON-5A human decision (scratch on D:, transient files only). |
| `completion_marker` | Text the `.sta` must contain (`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`) |
| `provenance` | Sources; not part of the profile hash |

**Profile hash:** the canonical hash of every field except `provenance`. A different
release, `cpus`, template or scratch policy gives a different hash, so solves are never
reused across profiles.

**Not yet used:** no real solve has been made with these profiles. Real Abaqus needs a
HUMAN gate.
