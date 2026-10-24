# M10 — SP-10 physical registration preparation

**Status: `READY_FOR_HUMAN_CONFIRMATION`.**

- The scan geometry of both sessions is reconstructed on the physical panel. Session 260831 needed a recorded
  deviation of one image-analysis constant (§3.2).
- The orientation of the FE model relative to the panel has eight physically admissible candidates. They are
  **not confirmed**, and only the owner's statements can resolve them (§6).

No registration was built. No MAC, frequency or mode shape was used anywhere: the candidates are geometric statements
only. No FE solve, Abaqus Python, Auto-ID or LM was run. No original and no verified copy was changed. Nothing here is
governed evidence, ACCEPTED, or production-ready.

Data, figures and tools are in `D:\git\abaqus-modal-comparator-work\runs\m10_sp10`. The figures are not committed,
because they are built from the user's PSV camera frames. The owner's review page is
`runs\m10_sp10\REVIEW_SP10_ORIENTATION.md`. The machine-readable summary is
[M10_SP10_REGISTRATION_PREP.json](M10_SP10_REGISTRATION_PREP.json).

## 1. Copies used and their verification

All inputs are verified copies, read only:

- `external_models\v2_20261019\SP-10` (`COPY_MANIFEST_V2.json`);
- the 260831 PolyMAX file extracted in M9 from the `sumin` zip (`runs\m9\polymax_zip_members\SP10_polymax.unv`; its
  SHA-256 equals the catalog).

`copy_verification_before.json` records **17 of 17 files equal to the manifests** before the work, and
`copy_verification_after.json` records the same after it.

| Role | File (copy) | SHA-256 |
|---|---|---|
| 260831 modal data | `SP10_polymax.unv` (set **Bravo**, 10 modes) | `b20549e6…` |
| 260831 PSV | `SP10_500by500_Glue420_Honeycomb_PlainFiber_260831.svd` | `16833e04…` |
| 260911 b modal data | `SP10_b_polymax.unv` (set **Bestttt**, 13 modes) | `497c7a47…` |
| 260911 b PSV | `SP10_b_rotated_500by500_Glue420_Honeycomb_PlainFiber_260911.svd` | `c1898e3a…` |
| Passport | `spec.txt` (520 × 515 × 2.8 mm; which side is 520 is not stated) | `b7256e96…` |
| FE model | `SP10_NEW_E1=E2_NSM_DENSITY.inp` (+ 3 INPs with the identical mesh) | `851ed627…` |

**Not among the copies:**

- the photograph `SR-10.jpg` named in the passport, or any other photograph of SP-10;
- any SP-10 FE extraction (`geometry.csv`, manifest or shape pack). None exists in the work data or the comparator
  cache.

## 2. Experimental data of the two sessions (kept separate)

| | 260831 | 260911 b |
|---|---|---|
| Points | 121 (11 × 11), pitch about 37.7 mm | 323 (17 × 19); **34 pairs 0.56 mm apart** (top and bottom rows doubled), 289 distinct positions, pitch about 23 mm |
| Measured DOF | +Z only (direction 3) | +Z only |
| UNV coordinates | metric scanner plane, z = −1 m; anisotropic: x 1.168, y 0.874 of physical | x 1.177, y 0.883 of physical |
| MeasPoints ↔ UNV (parser check, limit 2·10⁻³) | max 6.2·10⁻⁴ | max 7.2·10⁻⁴ |
| Experimental axes in the camera frame | +x = image right, +y = image up | the same |
| Other sets in the file | Processing (15) | Processing_polym (37), Nice (1) (12), Nice (14), Processing (15) |

## 3. Physical reconstruction (method of SP-02 / SP-13, M2.3)

### 3.1 Method

The method is `services.psv_video_registration.reconstruct` unchanged, the same code that produced the accepted SP-02
and SP-13 records:

1. the PSV MeasPoints are validated against the UNV;
2. the pixel normalisation comes from the stored full-frame rectangle;
3. the four panel edges are fitted in the stored camera frame;
4. a homography maps the frame to the panel, with the passport dimensions 520 × 515 mm.

Each session was run with both assignments of the 520 / 515 sides to the horizontal axis
(`reconstruction_<session>_W…xH….json`).

### 3.2 Session 260831: deviation of one constant (diagnostic)

**With the accepted constants, the bottom edge is fitted wrongly:**

- RMS is 10.1 px; the other edges fit within 0.18–0.39 px;
- the fitted line is 25–35 px below the real edge.

The reason is the scene below the panel. The dark shaker and its cable lie behind the bottom edge across most of its
width. The true edge (y ≈ 925–929 px) therefore collects only 31 of 120 edge samples, which is 26 %. The method's
cluster rule requires 30 % and so takes the shaker contour.

**The diagnostic variant** `EDGE_CLUSTER_MIN_SHARE = 0.25` changes only this constant:

- bottom-edge RMS 0.21 px;
- the camera-grid model residual against the reconstruction falls from 2.1 / 6.6 mm to 1.46 / 3.13 mm (median /
  maximum);
- in 260911 b the variant gives the identical result.

The variant is a deviation from the accepted method constants. It is recorded in every 260831 output, and using it for
a registration is a SUPERVISOR decision.

### 3.3 Results

| | 260831 (variant) | 260911 b |
|---|---|---|
| Edge RMS L / R / T / B, px | 0.18 / 0.39 / 0.24 / 0.21 | 0.49 / 0.36 / 0.20 / 0.13 |
| Horizontal × vertical, mm (§4) | **520 × 515** | **515 × 520** |
| Scan window, mm | 376.5 × 496.5 | 370.2 × 497.9 |
| Gap to edges L / R / B / T, mm | 76.5 / 67.0 / 8.3 / 10.2 | 71.8 / 73.0 / 9.4 / 12.7 |
| Camera-grid model residual, median / max, mm | 1.46 / 3.13 | 1.16 / 2.99 |
| Grid axis misalignment | 0.05° | 0.29° |

The residuals are smaller than in the accepted SP-02 (2.83 / 5.93 mm) and SP-13 (2.68 / 5.72 mm) records.

## 4. What the records establish about orientation

**Confirmed by the stored frames** (owner confirmation still requested):

1. The handwritten label "SP-10 / 500x500 / Plain fiber / Honey comb / DP-420" is legible, not mirrored, in both
   frames. **The labelled face faced the scanner in both sessions.**
2. The label is at the top right and upright in 260831. In 260911 b it is at the bottom right and turned 90° clockwise:
   rotating the crop 90° counter-clockwise makes it upright. **The panel was rotated 90° clockwise as seen by the
   scanner.** This is consistent with the file name `SP10_b_rotated`.
3. The red **"b-top"** mark lies on the top edge in 260911 b. That is edge A–D, the left edge in 260831. It is not
   visible in the 260831 frame, so it was most likely written for session b.
4. In both sessions the experimental +x points to the image right, +y to the image up, and +z towards the scanner; the
   DOF is +Z only.

**Indicated by the frame aspect** (a ruler confirmation is requested): the label edge D–C, horizontal in 260831, is
the **520 mm** edge. The evidence is in the table below.

| Ratio px/mm x / y | horizontal 520 | horizontal 515 |
|---|---|---|
| 260831 (variant) | **1.0008** | 1.0203 |
| 260911 b | 0.9792 | **0.9983** |
| Same rig, accepted: SP-02 1.0013, SP-13 1.003 | | |

- Only "260831 horizontal 520, 260911 b horizontal 515" agrees with the rig in both sessions, and that is exactly the
  90° rotation.
- The alternative requires the camera pixel aspect to change by 4 % between sessions.
- The panel sides differ by only 1 %, so this inference relies on image measurement. It needs a ruler.

**Not determinable from the records:**

- the FE in-plane sign: candidate pairs differ by 180°;
- which physical face is FE TOP or BOTTOM;
- the physical honeycomb wall direction: it is not visible through the face;
- which physical edge the model's X and Y were built from.

Corner naming used throughout, a proposal to be confirmed: **A–D** in the panel frame P, which is the labelled face
seen with the label upright:

- A — bottom left (origin);
- B — bottom right;
- C — top right, at the label;
- D — top left.

The edges are therefore A–B / D–C = 520 and A–D / B–C = 515. In 260911 b the view shows A top left, B bottom left,
C bottom right and D top right.

## 5. The SP-10 FE model (read from the INP text; no Abaqus)

- `SP10_NEW_E1=E2_NSM_DENSITY`, `SP10nemash63000`, `SP10newmash` and `SP10_new_E_NSM_DENS` have **identical node
  blocks and instance placements**: 1 667 491 INP nodes, node-block hash `08878169…`. Only the materials differ.
- `SP10.inp` is an older mesh. `SP_10.inp` has 1 663 816 nodes, which equals the accepted SP-02 model's node count.
- **Faces:** X 0–515 mm, Y 0–520 mm.
  - **FE TOP** = `CFRP_TOP-1`: 0.40 mm, z 2.39–2.79, measured side `max_z`, E 61 300 MPa.
  - **FE BOTTOM** = `CFRP_BOT-1`: 0.39 mm, z 0–0.39, `min_z`, E 62 800 MPa.
  - The thickness and the NSM (43.2 g / 41.52 g) match the passport's "top" and "bottom" face sheets. The passport
    does not say which of them carries the label.
- **Core** `SP02_Honeycomb_Core-1` (C3D20R):
  - placed at X 3–513, Y 2–517, z 0.39–2.39;
  - its **straight cell walls are parallel to FE Y** (`fig4_fe_model.png`).
- **Material orientation:** global axes, with E1 = E2 on the faces. The in-plane anisotropy of the model is therefore
  only the core lattice and the 515 / 520 plan.
- **Steps:** the INPs have **two frequency steps**: `Modal_FreeFree` (15 modes) and `SP_10_MODAL_FREE` (25 modes).
  An extraction must name the step.
- **FE geometry identity:** not available. No SP-10 ODB extraction exists, and Abaqus Python was not authorised. The
  surfaces taken from the INP (30 102 nodes each) are used here only for the geometric checks below. They are not an
  FE geometry identity.

## 6. Orientation candidates (none confirmed)

Panel frame P maps to FE as follows:

- 4 in-plane rotations × 2 faces = 8 candidates;
- the face is TOP if the labelled face is FE TOP (scanner on +Z), and BOTTOM with an in-plane mirror so that the
  determinant is +1;
- for 260911 b, the experimental axes follow from the confirmed 90° rotation: x_exp = +p_y, y_exp = −p_x.

| Candidate | P x / y in FE | Face | 260831 axes in FE | 260911 b axes in FE | Agrees with 520 / 515 by the frame |
|---|---|---|---|---|---|
| T0 | +X / +Y | TOP | +X +Y +Z | +Y −X +Z | no |
| **T90** | +Y / −X | TOP | +Y −X +Z | −X −Y +Z | **yes** |
| T180 | −X / −Y | TOP | −X −Y +Z | −Y +X +Z | no |
| **T270** | −Y / +X | TOP | −Y +X +Z | +X +Y +Z | **yes** |
| B0 | +X / −Y | BOTTOM | +X −Y −Z | −Y −X −Z | no |
| **B90** | +Y / +X | BOTTOM | +Y +X −Z | +X −Y −Z | **yes** |
| B180 | −X / +Y | BOTTOM | −X +Y −Z | +Y +X −Z | no |
| **B270** | −Y / −X | BOTTOM | −Y −X −Z | −X +Y −Z | **yes** |

**Geometry does not discriminate between the candidates.** Every candidate puts all points of both sessions on the
FE face within 2.1 mm of a node. The scan-window offsets of each candidate are in `orientation_candidates.json` and
in the evidence drafts.

**The 260831 counterpart of the SP-02 convention (+x → +X, +y → +Y), which is T0, contradicts the frame aspect.** The
accepted SP-02 registration therefore cannot be carried over to SP-10, even as a convention.

If the model's honeycomb follows the physical core, the frame-consistent candidates put the straight cell walls
parallel to the label edge D–C. That is checkable by the owner (Q5).

## 7. Guided registration (CORE-E2E-C): drafts only

- `runs\m10_sp10\evidence_DRAFT_SP10_260831.json` and `…_260911b.json` are `auto-id/guided-physical-evidence/v1`
  drafts.
- **Filled:**
  - the exact experimental SHA-256, size, modal set (`bravo` / `bestttt`), DOF `U3` and point count;
  - the camera-grid scan window and its provenance.
- **Explicitly unfilled:**
  - orientation (`experimental_axes_in_fe`);
  - the measured surface (instance, side);
  - panel-edge offsets;
  - the FE geometry identity;
  - uncertainty.
- The candidate values are attached separately as `m10_candidate_values`; they are never evidence.
- The existing parser `evidence_from_document` **refuses both drafts**, as it must.

**Blockers before a diagnostic registration can be built:**

1. the owner's statements Q1–Q6 below;
2. an FE geometry identity: extraction of the chosen SP-10 ODB, a HUMAN gate (Abaqus Python);
3. for 260911 b, the 34 pairs 0.56 mm apart land on shared FE nodes on the 3 mm face mesh. The CORE-E2E-C rule
   "every point on its own FE node" (`guided_registration.py:415`) refuses this file for **every** orientation. The
   rule was not changed; how to treat the doubled rows is a SUPERVISOR / HUMAN decision (Q7);
4. for 260831, acceptance of the one-constant method deviation (§3.2).

## 8. Questions for the owner (the main result)

The questions are kept in Russian because the owner will answer them; the same text and the figures are in
`runs\m10_sp10\REVIEW_SP10_ORIENTATION.md`.

1. **Длина кромки с надписью.** Длина кромки D–C, вдоль которой написано «SP-10 / 500x500 …» (верхняя, когда надпись
   читается прямо): 520 или 515 мм? По кадрам — 520; нужна линейка.
2. **Обозначения углов.** Подтвердить A–D: C — угол у надписи, A — противоположный. Желательно поставить физическую
   метку «A» и сфотографировать обе стороны.
3. **Сторона панели.** Подписанная сторона, которую лазер измерял в обеих сессиях, — это «верхняя» обшивка паспорта
   (0,40 мм, 161,5 г, CFRP_TOP-1), «нижняя» (0,39 мм, 163 г, CFRP_BOT-1) или неизвестно?
4. **Как строилась модель.** Какая физическая кромка заложена как X Abaqus (515 мм), какая как Y (520 мм), где начало
   (0, 0)? Выбрать T90 / T270 / B90 / B270 на рисунке 5 или указать, что модель строилась без привязки к кромке.
5. **Направление сот.** В реальной сердцевине прямые стенки параллельны кромке с надписью или перпендикулярны ей?
   (Фото сердцевины, ориентация печати, срез на торце.)
6. **Сессия b.** Подтвердить:
   - поворот на 90° по часовой стрелке со стороны сканера;
   - измерялась та же подписанная сторона;
   - «b-top» стоит на кромке A–D;
   - сканер и камера не перемещались.
7. **Повторяющиеся точки сессии b.** Задвоение верхнего и нижнего рядов (34 пары, 0,56 мм) сделано намеренно? Можно ли
   исключить дубли?
8. **Фотографии.** Прислать копии `SR-10.jpg` и фото установки или обеих сторон панели.

## 9. Figures (in `runs\m10_sp10`, not committed)

| File | Content |
|---|---|
| `fig1_260831_frame_overlay.png`, `fig1_260911b_frame_overlay.png` | Stored PSV frame: fitted edges, all points, experimental axes, corners A–D (proposed), label; for b also "b-top" and the doubled points; for 260831 the rejected accepted-constant bottom edge |
| `fig2_<session>_points_mm.png` | Point layout in mm on the panel, scan window, gaps to the edges |
| `fig3_both_sessions_panel_frame.png` | Both grids in the one panel frame P |
| `fig4_fe_model.png` | FE plan with X / Y, core outline, honeycomb wall direction, TOP / BOTTOM stack |
| `fig5_<session>_candidates.png` | The 8 candidates as seen by the scanner: FE origin, +X / +Y, FE wall direction; the ones contradicting 520 / 515 shown grey |

## 10. Erratum to M9 (§5.1)

**SP-10 FE rows 10–12 are reproducible.**

- The SP-10 jobs have a second frequency step, `SP_10_MODAL_FREE` (25 modes).
- Its modes 16–18 equal the Excel values exactly:
  - column C (`SP10nemash63000`): 228.43 / 266.44 / 268.56 Hz;
  - column D (`SP10_NEW_E1=E2_NSM_DENSITY`): 226.95 / 265.04 / 267.14 Hz.
- The M9 inventory read only the first eigenvalue table. No other `.dat` file in the copies has more than one table.
- The M9 statement "not reproducible" and the related bullet in M9 §6 are therefore withdrawn.
- The Excel rows remain a **rank** alignment, not MAC pairs.
- The merged M9 document is not edited here; this erratum and the CHANGELOG record the correction.

## 11. What did not change

- SPEC v1.2, DECISIONS, EVIDENCE, registrations, passports, frozen observations, criteria and gates.
- `services/psv_video_registration.py` and `services/guided_registration.py`: unchanged; the variant constant was set
  only in a run script under `runs\m10_sp10\tools`.
- No FE solve, no Abaqus Python, no Auto-ID, no LM, no mode pairing by frequency, and no MAC.
- M8 original gate `NOT_MET`; production calibration BLOCKED / NOT_AUTHORISED; D-077 NO_GLOBAL_PARAMETER_VALUE.
