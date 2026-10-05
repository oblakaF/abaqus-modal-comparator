# Validated FE shape packs (M4 ODB shape-extraction gate)

**Gate:** HUMAN-authorised 2026-10-04. Supervisor review: PASS.

**Scope:**
- Tier A: SP02 and SP13 CARBON-4C baselines.
- Tier B: SP13 CARBON-5A E± and G±.
- Measured outer surface only.

**Extraction:**
- Abaqus 2024 Python (`abq2024.bat python`) ran the pinned, unchanged
  `abaqus_scripts/extract_odb.py` (SHA-256 `039aa067…`), modes 7–30.
- It ran on SHA-verified scratch copies; the archived ODB originals were never opened
  by Abaqus and are unchanged.
- No solver runs.
- Raw extractions were temporary validation material and are not archived.

Each `<job_name>.shape-pack.json` (schema `auto-id/fe-shape-pack-record/v1`) pins one
pack in the `carbon-project-archive` store.

| Field | Meaning |
|---|---|
| `job_name`, `generated_inp_sha256` | The M3 content-addressed job (equal to the accepted forward-job anchors) |
| `odb` | Source ODB: store path, SHA-256, size |
| `pack` | Pack file `fe_shapes/<job>.npz`: SHA-256, size |
| `content_sha256` | Hash of the five arrays (name, dtype, shape, bytes); independent of zip layout |
| `node_set` | Passport measured surface (`<TOP instance>`, `max_z`, 1e-4 mm). Count and SHA-256 equal the FrozenRegistration's FE mapping-node subset. |
| `mode_numbers`, `frequencies_hz` | Modes 7–30 and the exact ODB eigenfrequencies (EIGFREQ) |
| `validation` | Gate checks V1–V8 (all PASS; V6 for baselines only) |
| `provenance_record` | Full gate provenance in the archive, pinned by SHA-256 |

**Pack format** (`auto-id/fe-shape-pack/v1`, `.npz` without pickle):

| Array | Content |
|---|---|
| `node_ids` | Sorted |
| `coordinates` | (n, 3) |
| `mode_numbers` | Mode numbers |
| `frequencies_hz` | Exact eigenfrequencies |
| `displacements` | (24, n, 3), float32; lossless, the ODB is single precision |

**Loading:** `services.fe_shape_pack.load_shape_pack(record, roots)` resolves the pack
from its store and checks size and file SHA-256. It then verifies the content hash,
node set, modes and frequencies against the record, and refuses any difference.

| Job | State | Nodes | Content SHA-256 |
|---|---|---|---|
| `SP02_f3e592281bebce66` | SP02 baseline | 29 583 | `b1a2f3567a2cfd53…` |
| `SP13_a46d08b52995e078` | SP13 baseline | 29 754 | `7941545b59390a65…` |
| `SP13_a9df66283a168786` | SP13 E −5 % | 29 754 | `371050a5ff4b4686…` |
| `SP13_0e861d03c333bb0b` | SP13 E +5 % | 29 754 | `bac951494c22c82e…` |
| `SP13_0328066b74b6fd78` | SP13 G12 −5 % | 29 754 | `b30263d23209e1fd…` |
| `SP13_4c0f189b9727feaf` | SP13 G12 +5 % | 29 754 | `1febd80145e25448…` |
| `SP13_bb3e5d7d131bed4f` | SP13 M4.9 twin truth (`TWIN_TRUTH`; M4.9 truth gate, not the extraction gate; provenance `m4_twin/SP13_truth_gate/`) | 29 754 | `758add0c22b824c5…` |

**Use so far:** M4.2 builds the complete baseline MAC matrix from these packs.

**Not yet used:**
- the SP13 ±5 % packs for M4.4 cluster confirmation or as a Jacobian;
- the baselines for M4.3 classifier validation.

Both need separate review.
