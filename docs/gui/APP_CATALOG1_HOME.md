# APP-CATALOG.1 — specimen passports on Home (2026-10-28)

Branch `feature/app-catalog1-specimen-passports-home` from `main` `e9dd517`. A read-only user-interface addition: no
FE calculation, import, MAC, registration, Auto-ID, threshold or scientific decision is changed.

## What the user sees

Home has a fifth area below the four existing ones: **5 Specimen catalogue / Паспорт образца**. It spans the full
width of Home and scrolls with it.

- **Specimen list.** The 14 physical specimens of the catalogue: SP-01 … SP-13 and SP-15, with type and family.
  SP-14 has no record in the catalogue and is not listed or created.
- **Passport.** Choosing a specimen shows its passport at once. Nothing else is read and no analysis runs. The passport
  has these sections:
  - **Identity and status:**
    - ID, type, family;
    - identity confidence with its evidence (and the identity resolution where the catalogue has one);
    - label text;
    - the specimen's Auto-ID status codes and its role.
  - **Dimensions:** panel plan, total thickness, top and bottom face sheets, core thickness, the local face-thickness
    variation and the dimension source.
  - **Materials:**
    - face material, stock and weave, and the nominal face thickness;
    - core material, topology, grade and process;
    - adhesive;
    - the status of the FE constants.
  - **Masses:**
    - face sheets, core and adhesive;
    - the finished panel, in each form the spec records (recorded, real, calculated).
  - **Experimental data:** one section per recorded data set, with the session, the data kind (raw FRF or PolyMAX
    fitted modes), the modal sets with mode counts and frequency spans, the governed set, the usability and the source
    file named by the catalogue (store, path, size, short hash).
  - **FE data:**
    - FE status and the governed FE model, or "none recorded";
    - the FE files named by the catalogue;
    - physical and legacy registration, with basis, distortion, open items and strict pairs.
  - **Origin of the data:** the spec file and specimen note named by the catalogue, the store folder, and the
    catalogue's status and acceptance.
- **Message line.** It shows the number of specimens and the catalogue status, then which passport is shown.

## Scientific distinctions kept on screen

| Kept apart | How it is shown |
|---|---|
| Recorded value vs calculated value | Every mass carries the qualifier the spec gives it: *recorded*, *recorded in the spec as the real value*, *recorded in the spec as a calculated value*. The program calculates no mass. |
| Nominal vs recorded thickness | *Nominal face* is "nominal stock thickness, not a measurement". *Total thickness* is "recorded total sandwich thickness, not a face-sheet thickness". |
| Material properties vs FE template constants | FE constants are shown by status only: "FE input values (ASSUMED/TEMPLATE), not measured or identified material properties". No constant value (E1, G12, …) is shown. |
| Raw FRF vs governed fitted modes | Raw FRF is "measured response functions, not fitted modes". A PolyMAX export is either "governed fixture set …" or "not governed (not a confirmed modal set)". |
| Existing ODB vs governed FE model | *Governed FE model* is the forward model of the catalogue or "none recorded". The listed INP/ODB files are separate. The section says that an existing INP or ODB is not a governed FE model. |
| Historical vs physical registration | *Physical registration* and *Legacy registration* are separate rows, each with the catalogue's status. |
| Catalogue acceptance vs specimen validation | "The catalogue is ACCEPTED as the inventory of the specimen records. That does not mean that every specimen is scientifically validated." Each specimen keeps its own status codes. |

- **Unknown values.** An unknown or `null` value is shown as **Неизвестно (unknown)**, never as zero. A missing mass,
  thickness or dimension is never derived from the others.
- **Values derived by the catalogue itself** keep its `DERIVED` note (core mass per area, core grade).
- **Two series of one specimen stay apart.** SP-13 260909 and 260910 a are separate sections. The active set *Best*
  (`SP13/best-physical`) belongs to 260910 a only.
- **SP-15** keeps its AMBIGUOUS identity and unknown dimensions, masses and stock. Nothing is taken from SP-12.
- **SP-12** shows "No experiment is recorded for this specimen in the catalogue."
- **Status values unchanged.** Every passport states that no material property of the specimen is identified
  (production Auto-ID is not authorised). M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and the production Auto-ID
  prohibition are unchanged.

## What choosing a specimen does not do

- **Inputs:** it sets no FE or experimental file, modal set or physical registration.
- **Analysis:** it changes no readiness state, result, MAC or project state, and starts nothing (no Abaqus, solver,
  LM or Auto-ID).
- **Files:** it reads no measurement file. It does not use the **File > Input file registry**, which is a separate list
  of the user's own input files.

The selection is Home's own variable. Loading a specimen's files for a comparison stays the user's own choice in
area 1.

## Data source and failures

- **Source.** The only source is `docs/auto_id/specimen_catalog.json`, read once when Home is built, read-only.
- **Files the catalogue names.** Spec files, UNV, ODB, registrations are only named, never opened. Paths are shown with
  the store root the catalogue records.
- **Missing or damaged catalogue.** The area shows a warning naming the problem and the path, the list is disabled, and
  the rest of the program works as before. Problems detected:
  - not found;
  - too large;
  - not JSON;
  - wrong schema;
  - no specimen list;
  - a record without ID;
  - a duplicate ID.
- **A damaged record** inside a valid catalogue is shown with unknown values instead of failing.
- **Runtime dependency.** The catalogue stays a documentation artifact (`runtime_dependency: false`). The program
  does not need it to run.

## Code

- **`src/services/specimen_catalog_view.py`** (new): `load_catalogue`, `passport_sections`, `experiment_sections`,
  `choice_text`. It has no Tk code, computes nothing and writes nothing.
- **`src/home_dashboard.py`:** `HomeDashboard._build_catalogue`, `show_passport`. The card is laid out full width below
  the four areas. The mouse wheel over the list scrolls Home and never changes the choice. No `install_*` layer was
  added.

## Validation

- **`tests/test_app_catalog1_home.py`** (25 tests). Service tests on the real catalogue (read-only) and on synthetic
  damaged inputs:
  - the 14 records, and SP-14 absent;
  - SP-02, SP-13, SP-12, SP-15;
  - each distinction in the table above;
  - unknown never zero, and nothing computed;
  - damaged catalogues and records;
  - only the catalogue file is read, and its hash is unchanged.

  Home tests on the real main window:
  - the list;
  - the four control passports;
  - choosing five specimens with an established result: inputs, modal set, result object, pairs, MAC matrix,
    analysis state, readiness rows, metric cards, project state and export state unchanged; registry read/write and
    Run patched to fail;
  - Home ↔ Expert keeps the passport and the analysis data;
  - the wheel over the list;
  - missing and damaged catalogue;
  - wrapping at four window sizes and interface scales.
- **`tests/test_app_ui1_home.py`:** the layout test now expects the fifth card (full width).
- **Windows GUI smoke.** `RUN_PROGRAM.cmd`, isolated profile, synthetic FE manifest and UNV, no analysis, no file
  dialog:
  - Home with the passports of SP-02, SP-13, SP-12 and SP-15, scrolled through;
  - Expert and back: the passport is kept;
  - files and readiness on Home unchanged;
  - no child process; exit code 0; inputs and catalogue unchanged.

## Limits

- **Language.** The passport uses the catalogue's own English wording. Only the area title and *Неизвестно* are
  bilingual.
- **Reload.** The catalogue is read once when the window opens. A changed catalogue is shown after a restart.
- **Display scaling.** Windows display scaling other than 100 % was not tried (the interface scale 80–125 % was).
