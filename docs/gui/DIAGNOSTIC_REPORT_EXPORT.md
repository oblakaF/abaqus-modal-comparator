# Diagnostic PDF / Excel report (CORE-E2E-D)

When an ODB + UNV analysis cannot establish the physical registration it ends as a diagnostic, with no comparison
result: `FREQUENCY_ONLY_DIAGNOSTIC` (ambiguous orientation, no reusable or guided registration), or an experimental file
without usable data. Such an analysis can now be saved as an engineering report.

## User path

On **2. Compare** (or **Reports**), the export buttons follow the result:

- **Established comparison:** **Export PDF report** / **Export Excel report**, unchanged.
- **Diagnostic:** **Export diagnostic PDF** / **Export diagnostic Excel**.

Both write the diagnostic report of the analysis shown when the export starts. The buttons are disabled while a new
analysis runs.

## Content

All content comes from the backend objects of that analysis:

- `LoadedModalData`;
- `FrequencyOnlyDiagnostic`;
- the `modal_data_viewer` classifications;
- the guided-registration evidence list.

| Section (PDF) / sheet (XLSX) | Content |
|---|---|
| Title, banner | *Abaqus–Experiment Modal Diagnostic Report*; **FREQUENCY-ONLY DIAGNOSTIC — PHYSICAL MODE PAIRING NOT ESTABLISHED** (or *EXPERIMENTAL DATA NOT USABLE*) |
| Sources / Summary | FE source (ODB or verified extraction manifest), sizes and SHA-256, ODB named by the extraction, step, FE geometry identity, FE modes and range, experimental file, source type, modal set, record count, measured DOFs, registration state, MAC `NOT_COMPUTED` |
| Why diagnostic | the backend reason, checks passed / not passed |
| What is needed | the physical evidence a registration needs, or an accepted registration of exactly these files |
| FE modes | mode number, frequency, points, components, shape information, extracted range |
| Experimental data | record, frequency, classification, source, modal set, warnings: out-of-range, spatial view, coherence, phase complexity, damping |
| Frequency diagnostic | nearest and next FE frequency and their frequency differences, range notes |
| Provenance | file identities, FE geometry identity, extraction, experimental metadata, generator |
| Images (PDF) | the separate FE / experimental views shown, captioned *not overlaid, not paired, no MAC* |

Classifications:

- **FITTED MODE** — curve-fitted modal set;
- **PROVISIONAL — FRF peak, NOT a validated fitted mode** — dataset 58.

In the frequency diagnostic:

- *Nearest frequency ≠ physical mode pairing.*
- MAC is `NOT_COMPUTED` and the pair column is `NONE`.
- The differences are frequency differences, not pair errors.

## Never in the report

- a MAC value, a mode pair, a pair frequency error, an orientation choice;
- an FIT / HOLDOUT observation;
- a material property.

## Robustness

- **Writing:** a temporary file next to the target is renamed into place, so no partial file is left. A file open in
  another program, or a folder that is not writable, is reported and the export can be repeated.
- **Save As:** the dialog opens in `Documents\Abaqus Modal Comparator Reports` (APP-UX.1,
  [REPORT_EXPORT_DIRECTORY.md](REPORT_EXPORT_DIRECTORY.md)); any other place can be chosen. Cancel writes nothing. A
  different typed extension gets the correct one appended, and an existing file is never replaced without
  confirmation.
- **Concurrency:** one export runs at a time. A new analysis started during an export does not change the report
  (snapshot), and the user is told.

## Validation (CORE-E2E-D, 2026-10-17)

Real GUI on verified copies, existing extraction caches, no Abaqus:

- **SP-02 / SP-13, accepted registration:** the comparison PDF / XLSX are unchanged (every workbook cell equal to the
  CORE-E2E report, same PDF page count).
- **New SP13_modal.odb without registration:** 12 fitted records, 19 FE modes; reason = FE geometry `b4015d13…` is not
  the accepted SP-13 geometry.
- **SP-04, dataset 58:** 19 PROVISIONAL FRF peaks; 8 outside the extracted FE range, marked.
- **Damaged experimental file:** FE-only report, `EXPERIMENTAL_DATA_NOT_USABLE`.

In every report: no numeric MAC, no pair status, frequencies equal to the loaded data (to the 15 significant digits of
the xlsx number format).
