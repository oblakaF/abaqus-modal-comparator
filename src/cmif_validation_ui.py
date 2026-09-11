from __future__ import annotations

from typing import Any, Dict

from polymax_ui import experimental_mode_source_label


_INSTALLED = False


def _source_and_confidence(result, experimental_mode_number: int):
    lookup = {mode.number: mode for mode in result.experimental.modes}
    mode = lookup.get(int(experimental_mode_number))
    if mode is None:
        return "Unknown", "—"
    metadata = mode.metadata
    source = experimental_mode_source_label(metadata)
    confidence = metadata.get("confidence_label") or "—"
    return str(source), str(confidence)


def validated_summary_text(result) -> str:
    information = result.experimental.metadata.get("close_mode_separation", {})
    clusters = information.get("clusters", [])
    lines = [
        f"Method: {information.get('method', 'not available')}",
        f"Excitation references: {information.get('reference_count', '—')}",
        f"SVD candidates before validation: {information.get('pre_validation_candidate_count', 0)}",
        f"Accepted SVD candidates: {information.get('added_mode_count', 0)}",
        f"Rejected SVD candidates: {information.get('rejected_mode_count', 0)}",
        "",
        "Automatic pairing policy:",
        str(information.get("automatic_pairing_policy", "not available")),
    ]

    for index, cluster in enumerate(clusters, start=1):
        targets = ", ".join(f"{float(value):.3f}" for value in cluster.get("cluster", [])) or "—"
        existing = ", ".join(
            f"{float(value):.3f}"
            for value in cluster.get("existing_peak_frequencies_hz", [])
        ) or "none"
        ratios = ", ".join(
            f"{float(value):.4f}"
            for value in cluster.get("singular_value_ratios", [])
        ) or "—"
        lines.extend(
            [
                "",
                f"Cluster {index}: Abaqus targets {targets} Hz",
                f"  retained FRF peaks: {existing} Hz",
                f"  local singular-value ratios: {ratios}",
            ]
        )
        for item in cluster.get("accepted_candidates", []):
            lines.append(
                "  ACCEPTED: "
                f"{float(item.get('frequency_hz', 0.0)):.3f} Hz | "
                f"confidence {item.get('confidence_label', '—')} "
                f"({float(item.get('confidence_score', 0.0)):.3f})"
            )
        for item in cluster.get("rejected_candidates", []):
            lines.append(
                "  REJECTED: "
                f"{float(item.get('frequency_hz', 0.0)):.3f} Hz | "
                f"{item.get('reason', 'unsupported candidate')}"
            )

    warning = information.get("scientific_warning")
    if warning:
        lines.extend(["", "Scientific interpretation:", str(warning)])

    abaqus_meta = result.abaqus.metadata
    experimental_meta = result.experimental.metadata
    lines.extend(
        [
            "",
            "Performance cache:",
            f"  ODB extraction reused: {abaqus_meta.get('extraction_cache_reused', '—')}",
            f"  Binary ODB dataset reused: {abaqus_meta.get('binary_odb_cache_reused', '—')}",
            f"  ODB dataset load: {float(abaqus_meta.get('odb_dataset_load_seconds', 0.0)):.3f} s",
            f"  UNV cache reused: {experimental_meta.get('unv_cache_reused', '—')}",
            f"  UNV load: {float(experimental_meta.get('unv_load_seconds', 0.0)):.3f} s",
        ]
    )
    return "\n".join(lines)


def install_cmif_validation_ui(cmif_ui_module, app_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    cmif_ui_module._summary_text = validated_summary_text
    application_class = app_module.ModalComparatorApp
    original_build_table = application_class._build_table
    original_populate = application_class._populate
    original_show_pair = application_class._show_pair

    def reviewed_build_table(self) -> None:
        original_build_table(self)
        columns = list(self.table["columns"])
        if "source" not in columns:
            columns.extend(["source", "confidence"])
            self.table.configure(columns=columns)
            self.table.heading("source", text="Experimental source")
            self.table.heading("confidence", text="Confidence")
            self.table.column("source", width=155, anchor="center")
            self.table.column("confidence", width=145, anchor="center")

    def reviewed_populate(self, result) -> None:
        original_populate(self, result)
        for item, pair in self.item_to_pair.items():
            source, confidence = _source_and_confidence(
                result, pair.experimental_mode
            )
            values = list(self.table.item(item, "values"))
            columns = list(self.table["columns"])
            while len(values) < len(columns):
                values.append("")
            values[columns.index("source")] = source
            values[columns.index("confidence")] = confidence
            self.table.item(item, values=values)

    def reviewed_show_pair(self, pair) -> None:
        original_show_pair(self, pair)
        if self.result is None:
            return
        source, confidence = _source_and_confidence(
            self.result, pair.experimental_mode
        )
        title = str(self.pair_title.cget("text"))
        suffix = f" | source: {source} | confidence: {confidence}"
        if suffix not in title:
            self.pair_title.configure(text=title + suffix)

    application_class._build_table = reviewed_build_table
    application_class._populate = reviewed_populate
    application_class._show_pair = reviewed_show_pair
    _INSTALLED = True
