from __future__ import annotations

from typing import List, Sequence, Tuple

HelpTopic = Tuple[str, str]

# One topic per tab/panel a user actually sees, in the order the tabs appear
# once every install_* layer in main.py has run. Keep titles short (they are
# the search-result list) and bodies plain-language, matching the words used
# in the real widgets rather than internal code names.
HELP_TOPICS: List[HelpTopic] = [
    (
        "Overview: what this program does",
        "Compares Abaqus modal-analysis results (.odb) with Siemens LMS / Simcenter "
        "Testlab measurements (.unv or .uff). It matches Abaqus and experimental mode "
        "shapes one to one, computes the Modal Assurance Criterion (MAC) and frequency "
        "error for every matched pair, and produces Excel and PDF reports. No manual "
        "frequency entry or Abaqus screenshots are required.",
    ),
    (
        "1. Files and analysis",
        "The starting tab. Select the Abaqus .odb (or a previously extracted "
        "manifest.json), the Simcenter .unv/.uff/.lms file, and the output workspace "
        "folder where the extraction cache, plots, and logs are written. The Abaqus "
        "command field must match how Abaqus is invoked on this machine (for example "
        "abaqus or abq2024). The Abaqus mode range narrows which modes are extracted "
        "from the ODB; experimental modes are always detected automatically. Press "
        "'Extract, compare, and build report data' to run the analysis; 'Open output "
        "folder' opens the workspace in Explorer once it exists.",
    ),
    (
        "Project: New, Open, Save",
        "File menu: New project clears all inputs and results and starts over. Open "
        "project... loads a saved .amcp.json project file, restoring the selected "
        "files, mode range, and any manual review decisions. Save project writes to "
        "the current project file (or asks for a location the first time); Save "
        "project as... always asks for a new location. The current project name is "
        "shown at the top of the window. Saving a project does not save the analysis "
        "results themselves, only the inputs and manual decisions needed to reproduce "
        "them; closing the window also saves a session file automatically so the next "
        "launch can restore where you left off.",
    ),
    (
        "2. Comparison table",
        "One row per accepted Abaqus/experimental mode pair: both frequencies, the "
        "signed frequency error (positive means Abaqus is higher/stiffer, negative "
        "means Abaqus is lower/softer), MAC, whether the mode order changed between "
        "the two datasets, how many geometry points were mapped, and a plain-language "
        "status such as 'Excellent match' or 'Review'. Selecting a row updates the "
        "Mode shapes tab. The metric labels above the table (matched pairs, mean "
        "frequency error, mean MAC, geometry match) summarize the whole comparison. "
        "'Export Excel report' and 'Export PDF report' generate the full reports from "
        "this result.",
    ),
    (
        "3. Mode shapes",
        "Side-by-side plots of the Abaqus mode shape, the experimental mode shape, and "
        "an overlay correlation plot for whichever pair is selected in the Comparison "
        "table (or the Manual review tab). Colors show normalized modal amplitude on a "
        "shared scale so the two shapes can be compared visually, not just by the MAC "
        "number.",
    ),
    (
        "4. MAC and frequencies",
        "Two whole-model plots: the full MAC matrix between every Abaqus mode and "
        "every experimental mode (not just the accepted pairs), and the frequency "
        "regression plot with a 45-degree perfect-agreement line and a fitted slope. A "
        "slope above 1 means Abaqus is generally stiffer/higher than the test; below 1 "
        "means generally softer/lower.",
    ),
    (
        "5. FRF & quality",
        "Diagnostics for the automatic quality-control decisions. The left plot shows "
        "the combined experimental FRF indicator with coherence overlaid, marking which "
        "peaks were matched (solid lines) and which were not (faint lines). The right "
        "plot shows the verified-pair MAC submatrix, i.e. MAC only among modes that "
        "were actually accepted. The summary panel lists excluded near-zero (rigid) "
        "modes, unmatched Abaqus modes, unmatched experimental peak candidates, closely "
        "spaced Abaqus mode groups, and the accepted-pair admissibility limits "
        "(frequency error and MAC thresholds) that were applied before matching.",
    ),
    (
        "6. Close modes - SVD",
        "Local response-matrix SVD diagnostics for overlapping resonance bands, used "
        "when two or more Abaqus modes fall inside one experimental peak and would "
        "otherwise be indistinguishable from raw FRF data. The plot shows the "
        "energy profile of each locally separated SVD component. The panel below the "
        "plot lists the method used, how many additional close-mode candidates were "
        "found and their frequencies, and whether coherence-based weighting could be "
        "computed for this dataset; if it could not, split components may be "
        "under-detected rather than falsely confirmed. Use 'Expand description' to see "
        "the full text without scrolling, and 'Save summary...' to keep the full report "
        "regardless of whether it is expanded. With a single excitation reference this "
        "separation is diagnostic only, not a full multi-reference modal fit: confirm "
        "split modes by MAC, AutoMAC, coherence, and visual inspection.",
    ),
    (
        "7. AutoMAC & COMAC",
        "AutoMAC compares each dataset against itself: high off-diagonal AutoMAC means "
        "the measurement grid is too coarse to reliably distinguish some mode shapes, "
        "independent of how good the Abaqus correlation is. COMAC breaks correlation "
        "down by measurement location, identifying specific points where Abaqus and "
        "experiment disagree consistently across modes. The summary numbers highlight "
        "the worst off-diagonal AutoMAC value and the mean/minimum COMAC.",
    ),
    (
        "8. Manual review",
        "Automatic pairing is never overwritten in place; manual decisions layer on "
        "top of it to form the effective pair set used by the table, plots, and "
        "reports. Every elastic Abaqus mode is listed here, including ones the "
        "automatic assignment left unmatched. For each mode you can accept the "
        "automatic pairing, reassign it to a different experimental mode, reject it, "
        "or leave it unresolved with a comment explaining why (for example, 'needs a "
        "curve-fitted Testlab mode'). These decisions are part of the saved project "
        "file, so they survive closing and reopening the application.",
    ),
    (
        "9. Details",
        "The full text summary of the analysis: source file paths, geometry alignment "
        "(coordinate scale, matched fraction, mapping distances), every warning raised "
        "during comparison, the experimental mode list with damping and modal mass, raw "
        "Abaqus and experimental metadata, and any Abaqus modal history output found in "
        "the ODB. This is the same information exported to Excel and PDF, useful for "
        "copy-pasting into a report or an email.",
    ),
    (
        "Coordinate scale and geometry alignment",
        "The importer detects coordinate scale, axis order, and axis signs "
        "automatically by testing candidate rotations/scales and keeping the one with "
        "the best geometry fit. Leave the scale as 'auto' unless the experimental grid "
        "only covers part of the specimen, in which case automatic detection can be "
        "unreliable; enter a known scale such as 0.001 for millimeters-to-meters. "
        "Warnings about reflected transformations (mirrored geometry) or experimental "
        "points that map to an already-used Abaqus node appear in the FRF & quality tab "
        "and the Details tab, and mean the alignment should be checked before trusting "
        "MAC values.",
    ),
    (
        "MAC, frequency error, and admissibility limits",
        "MAC (Modal Assurance Criterion) is computed only on degrees of freedom that "
        "were actually measured experimentally, not the full 3D vector, so a high MAC "
        "confirms similarity only over the measured directions. Frequency error is "
        "signed: positive means the Abaqus frequency is higher than the experimental "
        "one, negative means it is lower. Before one-to-one matching, a pair must "
        "satisfy: |frequency error| <= 15% and MAC >= 0.50 (or, when MAC cannot be "
        "calculated, |frequency error| <= 10%). Modes that fail these limits are left "
        "unmatched rather than forced into a bad pair.",
    ),
    (
        "Reports: Excel and PDF export",
        "Both formats are built from the completed analysis, so run the analysis "
        "first. Excel includes the summary and source files, signed and absolute "
        "frequency errors, the mode-pair table, full and verified-pair MAC matrices, "
        "FRF/coherence diagnostics, geometry mapping distances, quality-control "
        "decisions, AutoMAC/COMAC, and the Abaqus modal history output. PDF includes "
        "summary pages, the frequency regression plot, MAC, FRF diagnostics, "
        "quality-control decisions, AutoMAC/COMAC, and one page per accepted mode "
        "pair. Use File > Export Excel report / Export PDF report, or the matching "
        "buttons on the Comparison table tab.",
    ),
    (
        "Troubleshooting: analysis failed",
        "If the analysis fails, the status bar points to last_error.log in the output "
        "workspace, which has the full error. A common cause is the Abaqus command not "
        "matching the installed release (try the exact command you would type to start "
        "Abaqus, such as abq2024, instead of the generic 'abaqus'). For the "
        "experimental file, confirm the .unv/.uff actually contains geometry (dataset "
        "15 or 2411) and either curve-fitted modes (dataset 55/2414) or raw FRFs "
        "(dataset 58); an .lms file only works when its companion UNV/UFF sits beside "
        "it. See docs/TROUBLESHOOTING.md in the project folder for more detail.",
    ),
]


def filter_help_topics(
    topics: Sequence[HelpTopic],
    query: str,
) -> List[HelpTopic]:
    """Return topics whose title or body contains every word in *query*.

    An empty or whitespace-only query returns every topic, in the original
    (tab) order. Matching is case-insensitive and requires all words to be
    present somewhere in the topic (title or body), in any order, so a
    two-word query such as "close mode" finds the SVD topic even though that
    exact phrase is not a substring of its title.
    """
    words = query.lower().split()
    if not words:
        return list(topics)
    matches = []
    for title, body in topics:
        haystack = f"{title}\n{body}".lower()
        if all(word in haystack for word in words):
            matches.append((title, body))
    return matches
