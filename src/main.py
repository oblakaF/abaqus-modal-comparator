from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageTk
except ImportError:  # The launcher installs Pillow automatically.
    Image = None
    ImageTk = None


FrequencyRow = Tuple[int, float]
ComparisonRow = Dict[str, object]

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}


def read_frequency_csv(file_path: Path) -> List[FrequencyRow]:
    """
    Read modal frequencies from a CSV file.

    Required columns:
        mode
        frequency_hz
    """
    rows: List[FrequencyRow] = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames is None:
            raise ValueError("The CSV file does not contain a header row.")

        normalized_fields = {
            field.strip().lower(): field
            for field in reader.fieldnames
            if field is not None
        }

        if "mode" not in normalized_fields:
            raise ValueError("The CSV file does not contain a 'mode' column.")

        if "frequency_hz" not in normalized_fields:
            raise ValueError(
                "The CSV file does not contain a 'frequency_hz' column."
            )

        mode_field = normalized_fields["mode"]
        frequency_field = normalized_fields["frequency_hz"]

        for line_number, row in enumerate(reader, start=2):
            mode_text = str(row.get(mode_field, "")).strip()
            frequency_text = str(row.get(frequency_field, "")).strip()

            if not mode_text and not frequency_text:
                continue

            try:
                mode = int(float(mode_text))
                frequency = float(frequency_text)
            except ValueError as error:
                raise ValueError(
                    f"Invalid data on line {line_number}: "
                    f"mode='{mode_text}', frequency_hz='{frequency_text}'."
                ) from error

            if frequency <= 0:
                raise ValueError(
                    f"The frequency on line {line_number} must be greater than zero."
                )

            rows.append((mode, frequency))

    if not rows:
        raise ValueError("No modal-frequency rows were found in the CSV file.")

    rows.sort(key=lambda item: item[0])
    return rows


def frequency_error(
    abaqus_frequency: float,
    experimental_frequency: float,
) -> float:
    """Calculate the absolute relative frequency difference in percent."""
    return (
        abs(abaqus_frequency - experimental_frequency)
        / experimental_frequency
        * 100.0
    )


def optimal_frequency_matching(
    abaqus_rows: List[FrequencyRow],
    experimental_rows: List[FrequencyRow],
) -> List[Tuple[FrequencyRow, FrequencyRow]]:
    """
    Find a one-to-one mode matching with the minimum total frequency error.

    Dynamic programming is suitable for the planned set of nine modes.
    """
    if not abaqus_rows:
        raise ValueError("The Abaqus mode list is empty.")

    if not experimental_rows:
        raise ValueError("The experimental mode list is empty.")

    rows_are_abaqus = len(abaqus_rows) <= len(experimental_rows)

    if rows_are_abaqus:
        small_rows = abaqus_rows
        large_rows = experimental_rows
    else:
        small_rows = experimental_rows
        large_rows = abaqus_rows

    if len(large_rows) > 18:
        raise ValueError(
            "The first version supports no more than 18 modes in one file."
        )

    @lru_cache(maxsize=None)
    def solve(
        row_index: int,
        used_mask: int,
    ) -> Tuple[float, Tuple[Tuple[int, int], ...]]:
        if row_index == len(small_rows):
            return 0.0, ()

        best_cost = float("inf")
        best_pairs: Tuple[Tuple[int, int], ...] = ()

        for column_index in range(len(large_rows)):
            if used_mask & (1 << column_index):
                continue

            _, small_frequency = small_rows[row_index]
            _, large_frequency = large_rows[column_index]

            if rows_are_abaqus:
                abaqus_frequency = small_frequency
                experimental_frequency = large_frequency
            else:
                abaqus_frequency = large_frequency
                experimental_frequency = small_frequency

            local_cost = frequency_error(
                abaqus_frequency,
                experimental_frequency,
            )

            remaining_cost, remaining_pairs = solve(
                row_index + 1,
                used_mask | (1 << column_index),
            )

            total_cost = local_cost + remaining_cost

            if total_cost < best_cost:
                best_cost = total_cost
                best_pairs = (
                    (row_index, column_index),
                ) + remaining_pairs

        return best_cost, best_pairs

    _, index_pairs = solve(0, 0)

    matched_rows: List[Tuple[FrequencyRow, FrequencyRow]] = []

    for small_index, large_index in index_pairs:
        if rows_are_abaqus:
            abaqus_item = small_rows[small_index]
            experimental_item = large_rows[large_index]
        else:
            abaqus_item = large_rows[large_index]
            experimental_item = small_rows[small_index]

        matched_rows.append((abaqus_item, experimental_item))

    matched_rows.sort(key=lambda pair: pair[0][0])
    return matched_rows


def create_comparison_rows(
    abaqus_rows: List[FrequencyRow],
    experimental_rows: List[FrequencyRow],
) -> List[ComparisonRow]:
    matched_rows = optimal_frequency_matching(
        abaqus_rows,
        experimental_rows,
    )

    abaqus_rank = {
        mode: rank
        for rank, (mode, _) in enumerate(
            sorted(abaqus_rows, key=lambda item: item[1]),
            start=1,
        )
    }

    experimental_rank = {
        mode: rank
        for rank, (mode, _) in enumerate(
            sorted(experimental_rows, key=lambda item: item[1]),
            start=1,
        )
    }

    results: List[ComparisonRow] = []

    for abaqus_item, experimental_item in matched_rows:
        abaqus_mode, abaqus_frequency = abaqus_item
        experimental_mode, experimental_frequency = experimental_item

        error_percent = frequency_error(
            abaqus_frequency,
            experimental_frequency,
        )

        order_changed = (
            abaqus_rank[abaqus_mode]
            != experimental_rank[experimental_mode]
        )

        if error_percent <= 5.0:
            status = "Match"
        elif error_percent <= 10.0:
            status = "Check"
        else:
            status = "Large difference"

        results.append(
            {
                "abaqus_mode": abaqus_mode,
                "experimental_mode": experimental_mode,
                "abaqus_frequency": abaqus_frequency,
                "experimental_frequency": experimental_frequency,
                "error_percent": error_percent,
                "order_changed": "Yes" if order_changed else "No",
                "status": status,
            }
        )

    return results


def normalize_stem(value: str) -> str:
    """Normalize a file stem for flexible image-name matching."""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def find_mode_image(
    folder: Optional[Path],
    mode_number: int,
    source_name: str,
) -> Optional[Path]:
    """
    Find an image for a mode.

    Recommended names include:
        abaqus_mode_6.png
        experimental_mode_1.jpg
        mode_6.png
        mode6.png
        6.png

    The Abaqus and experimental images are selected from separate folders.
    """
    if folder is None or not folder.exists():
        return None

    source = normalize_stem(source_name)
    exact_stems = [
        f"{source}_mode_{mode_number}",
        f"{source}_mode{mode_number}",
        f"{source}_{mode_number}",
        f"mode_{mode_number}",
        f"mode{mode_number}",
        str(mode_number),
    ]

    image_files = sorted(
        (
            path
            for path in folder.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ),
        key=lambda path: str(path).lower(),
    )

    normalized_files = {
        normalize_stem(path.stem): path
        for path in image_files
    }

    for stem in exact_stems:
        candidate = normalized_files.get(normalize_stem(stem))
        if candidate is not None:
            return candidate

    mode_pattern = re.compile(rf"(^|_){mode_number}($|_)")

    source_matches = [
        path
        for path in image_files
        if source in normalize_stem(path.stem)
        and mode_pattern.search(normalize_stem(path.stem))
    ]
    if source_matches:
        return source_matches[0]

    generic_matches = [
        path
        for path in image_files
        if mode_pattern.search(normalize_stem(path.stem))
    ]
    if generic_matches:
        return generic_matches[0]

    return None


class ModalComparatorApp:
    PREVIEW_SIZE = (430, 320)

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Abaqus Modal Comparator")
        self.root.geometry("1500x820")
        self.root.minsize(1150, 680)

        self.abaqus_file: Optional[Path] = None
        self.experimental_file: Optional[Path] = None
        self.abaqus_images_folder: Optional[Path] = None
        self.experimental_images_folder: Optional[Path] = None
        self.comparison_results: List[ComparisonRow] = []

        self.table_item_to_result: Dict[str, ComparisonRow] = {}
        self.abaqus_photo: Any = None
        self.experimental_photo: Any = None

        self.build_interface()

    def build_interface(self) -> None:
        title = tk.Label(
            self.root,
            text="Abaqus Modal Comparator",
            font=("Arial", 20, "bold"),
        )
        title.pack(pady=(15, 2))

        subtitle = tk.Label(
            self.root,
            text=(
                "Comparison of numerical and experimental "
                "frequencies and mode-shape images"
            ),
            font=("Arial", 11),
        )
        subtitle.pack(pady=(0, 10))

        input_frame = ttk.LabelFrame(
            self.root,
            text="Input data",
            padding=10,
        )
        input_frame.pack(fill="x", padx=18, pady=4)

        self.abaqus_label = self.create_file_row(
            input_frame,
            row=0,
            button_text="Select Abaqus frequency CSV",
            command=self.select_abaqus_file,
        )

        self.experimental_label = self.create_file_row(
            input_frame,
            row=1,
            button_text="Select experimental frequency CSV",
            command=self.select_experimental_file,
        )

        self.abaqus_images_label = self.create_file_row(
            input_frame,
            row=2,
            button_text="Select Abaqus images folder",
            command=self.select_abaqus_images_folder,
        )

        self.experimental_images_label = self.create_file_row(
            input_frame,
            row=3,
            button_text="Select experimental images folder",
            command=self.select_experimental_images_folder,
        )

        buttons_frame = tk.Frame(self.root)
        buttons_frame.pack(pady=9)

        compare_button = tk.Button(
            buttons_frame,
            text="Compare frequencies",
            command=self.compare_frequencies,
            width=25,
            height=2,
        )
        compare_button.pack(side="left", padx=7)

        self.export_button = tk.Button(
            buttons_frame,
            text="Export comparison CSV",
            command=self.export_results,
            width=25,
            height=2,
            state="disabled",
        )
        self.export_button.pack(side="left", padx=7)

        content_pane = ttk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
        )
        content_pane.pack(
            fill="both",
            expand=True,
            padx=18,
            pady=(0, 8),
        )

        table_frame = ttk.LabelFrame(
            content_pane,
            text="Mode matching results",
            padding=8,
        )
        preview_frame = ttk.LabelFrame(
            content_pane,
            text="Mode-shape image preview",
            padding=8,
        )

        content_pane.add(table_frame, weight=3)
        content_pane.add(preview_frame, weight=2)

        self.build_results_table(table_frame)
        self.build_image_preview(preview_frame)

        self.summary_label = tk.Label(
            self.root,
            text="No results have been calculated yet.",
            font=("Arial", 10, "bold"),
        )
        self.summary_label.pack(pady=(0, 6))

        self.status_label = tk.Label(
            self.root,
            text="Ready.",
            anchor="w",
            relief="sunken",
            padx=10,
        )
        self.status_label.pack(side="bottom", fill="x")

    def build_results_table(self, parent: tk.Widget) -> None:
        columns = (
            "abaqus_mode",
            "experimental_mode",
            "abaqus_frequency",
            "experimental_frequency",
            "error_percent",
            "order_changed",
            "status",
        )

        self.results_table = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            height=14,
            selectmode="browse",
        )

        headings = {
            "abaqus_mode": "Abaqus mode",
            "experimental_mode": "Experimental mode",
            "abaqus_frequency": "Abaqus, Hz",
            "experimental_frequency": "Experiment, Hz",
            "error_percent": "Error, %",
            "order_changed": "Order changed",
            "status": "Result",
        }

        widths = {
            "abaqus_mode": 95,
            "experimental_mode": 135,
            "abaqus_frequency": 105,
            "experimental_frequency": 120,
            "error_percent": 85,
            "order_changed": 105,
            "status": 120,
        }

        for column in columns:
            self.results_table.heading(
                column,
                text=headings[column],
            )
            self.results_table.column(
                column,
                width=widths[column],
                anchor="center",
                stretch=True,
            )

        vertical_scrollbar = ttk.Scrollbar(
            parent,
            orient="vertical",
            command=self.results_table.yview,
        )
        horizontal_scrollbar = ttk.Scrollbar(
            parent,
            orient="horizontal",
            command=self.results_table.xview,
        )

        self.results_table.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )

        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        self.results_table.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        vertical_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        horizontal_scrollbar.grid(
            row=1,
            column=0,
            sticky="ew",
        )

        self.results_table.bind(
            "<<TreeviewSelect>>",
            self.show_selected_mode_images,
        )

    def build_image_preview(self, parent: tk.Widget) -> None:
        self.preview_instruction = tk.Label(
            parent,
            text=(
                "Select a matched row in the table to display "
                "the corresponding mode-shape images."
            ),
            wraplength=560,
            justify="center",
        )
        self.preview_instruction.pack(fill="x", pady=(0, 8))

        cards_frame = tk.Frame(parent)
        cards_frame.pack(fill="both", expand=True)
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_columnconfigure(1, weight=1)
        cards_frame.grid_rowconfigure(0, weight=1)

        abaqus_card = ttk.LabelFrame(
            cards_frame,
            text="Abaqus mode shape",
            padding=6,
        )
        abaqus_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 4),
        )

        experimental_card = ttk.LabelFrame(
            cards_frame,
            text="Experimental mode shape",
            padding=6,
        )
        experimental_card.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(4, 0),
        )

        self.abaqus_image_title = tk.Label(
            abaqus_card,
            text="No mode selected",
            font=("Arial", 10, "bold"),
        )
        self.abaqus_image_title.pack(fill="x", pady=(0, 5))

        self.abaqus_image_label = tk.Label(
            abaqus_card,
            text="No image loaded",
            bg="white",
            relief="sunken",
            anchor="center",
            justify="center",
        )
        self.abaqus_image_label.pack(
            fill="both",
            expand=True,
        )

        self.abaqus_image_path_label = tk.Label(
            abaqus_card,
            text="",
            wraplength=280,
            justify="center",
        )
        self.abaqus_image_path_label.pack(fill="x", pady=(5, 0))

        self.experimental_image_title = tk.Label(
            experimental_card,
            text="No mode selected",
            font=("Arial", 10, "bold"),
        )
        self.experimental_image_title.pack(fill="x", pady=(0, 5))

        self.experimental_image_label = tk.Label(
            experimental_card,
            text="No image loaded",
            bg="white",
            relief="sunken",
            anchor="center",
            justify="center",
        )
        self.experimental_image_label.pack(
            fill="both",
            expand=True,
        )

        self.experimental_image_path_label = tk.Label(
            experimental_card,
            text="",
            wraplength=280,
            justify="center",
        )
        self.experimental_image_path_label.pack(fill="x", pady=(5, 0))

    @staticmethod
    def create_file_row(
        parent: tk.Widget,
        row: int,
        button_text: str,
        command,
    ) -> tk.Label:
        button = tk.Button(
            parent,
            text=button_text,
            command=command,
            width=34,
        )
        button.grid(
            row=row,
            column=0,
            padx=(0, 12),
            pady=4,
        )

        label = tk.Label(
            parent,
            text="Not selected",
            anchor="w",
        )
        label.grid(
            row=row,
            column=1,
            sticky="ew",
        )

        parent.grid_columnconfigure(1, weight=1)
        return label

    def select_abaqus_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select the Abaqus frequency CSV file",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            self.abaqus_file = Path(filename)
            self.abaqus_label.config(text=str(self.abaqus_file))
            self.status_label.config(
                text="Abaqus frequency file selected."
            )

    def select_experimental_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select the experimental frequency CSV file",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            self.experimental_file = Path(filename)
            self.experimental_label.config(
                text=str(self.experimental_file)
            )
            self.status_label.config(
                text="Experimental frequency file selected."
            )

    def select_abaqus_images_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Select the folder containing Abaqus mode-shape images"
        )

        if folder:
            self.abaqus_images_folder = Path(folder)
            self.abaqus_images_label.config(
                text=str(self.abaqus_images_folder)
            )
            self.status_label.config(
                text="Abaqus mode-image folder selected."
            )
            self.refresh_selected_mode_images()

    def select_experimental_images_folder(self) -> None:
        folder = filedialog.askdirectory(
            title=(
                "Select the folder containing experimental "
                "mode-shape images"
            )
        )

        if folder:
            self.experimental_images_folder = Path(folder)
            self.experimental_images_label.config(
                text=str(self.experimental_images_folder)
            )
            self.status_label.config(
                text="Experimental mode-image folder selected."
            )
            self.refresh_selected_mode_images()

    def clear_table(self) -> None:
        self.table_item_to_result.clear()
        for item_id in self.results_table.get_children():
            self.results_table.delete(item_id)

    def clear_image_preview(self) -> None:
        self.abaqus_photo = None
        self.experimental_photo = None

        self.abaqus_image_title.config(text="No mode selected")
        self.experimental_image_title.config(text="No mode selected")

        self.abaqus_image_label.config(
            image="",
            text="No image loaded",
        )
        self.experimental_image_label.config(
            image="",
            text="No image loaded",
        )

        self.abaqus_image_path_label.config(text="")
        self.experimental_image_path_label.config(text="")

    def compare_frequencies(self) -> None:
        if self.abaqus_file is None:
            messagebox.showwarning(
                "File not selected",
                "Select the CSV file containing Abaqus frequencies.",
            )
            return

        if self.experimental_file is None:
            messagebox.showwarning(
                "File not selected",
                "Select the CSV file containing experimental frequencies.",
            )
            return

        try:
            abaqus_rows = read_frequency_csv(self.abaqus_file)
            experimental_rows = read_frequency_csv(
                self.experimental_file
            )

            self.comparison_results = create_comparison_rows(
                abaqus_rows,
                experimental_rows,
            )

        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Data error",
                str(error),
            )
            self.status_label.config(
                text="The comparison could not be completed."
            )
            return

        self.clear_table()
        self.clear_image_preview()

        first_item_id: Optional[str] = None

        for result in self.comparison_results:
            item_id = self.results_table.insert(
                "",
                "end",
                values=(
                    result["abaqus_mode"],
                    result["experimental_mode"],
                    f'{result["abaqus_frequency"]:.3f}',
                    f'{result["experimental_frequency"]:.3f}',
                    f'{result["error_percent"]:.2f}',
                    result["order_changed"],
                    result["status"],
                ),
            )
            self.table_item_to_result[item_id] = result

            if first_item_id is None:
                first_item_id = item_id

        average_error = sum(
            float(result["error_percent"])
            for result in self.comparison_results
        ) / len(self.comparison_results)

        maximum_error = max(
            float(result["error_percent"])
            for result in self.comparison_results
        )

        self.summary_label.config(
            text=(
                f"Matched modes: {len(self.comparison_results)} | "
                f"Mean error: {average_error:.2f}% | "
                f"Maximum error: {maximum_error:.2f}%"
            )
        )

        self.export_button.config(state="normal")
        self.status_label.config(
            text="Frequency comparison completed successfully."
        )

        if first_item_id is not None:
            self.results_table.selection_set(first_item_id)
            self.results_table.focus(first_item_id)
            self.results_table.see(first_item_id)
            self.show_selected_mode_images()

    def show_selected_mode_images(self, _event: object = None) -> None:
        selected_items = self.results_table.selection()
        if not selected_items:
            return

        result = self.table_item_to_result.get(selected_items[0])
        if result is None:
            return

        abaqus_mode = int(result["abaqus_mode"])
        experimental_mode = int(result["experimental_mode"])
        abaqus_frequency = float(result["abaqus_frequency"])
        experimental_frequency = float(
            result["experimental_frequency"]
        )

        self.abaqus_image_title.config(
            text=(
                f"Abaqus mode {abaqus_mode} — "
                f"{abaqus_frequency:.3f} Hz"
            )
        )
        self.experimental_image_title.config(
            text=(
                f"Experimental mode {experimental_mode} — "
                f"{experimental_frequency:.3f} Hz"
            )
        )

        abaqus_image_path = find_mode_image(
            self.abaqus_images_folder,
            abaqus_mode,
            "abaqus",
        )
        experimental_image_path = find_mode_image(
            self.experimental_images_folder,
            experimental_mode,
            "experimental",
        )

        self.abaqus_photo = self.display_image(
            image_path=abaqus_image_path,
            image_label=self.abaqus_image_label,
            path_label=self.abaqus_image_path_label,
            folder=self.abaqus_images_folder,
            folder_description="Abaqus images folder",
            mode_number=abaqus_mode,
        )

        self.experimental_photo = self.display_image(
            image_path=experimental_image_path,
            image_label=self.experimental_image_label,
            path_label=self.experimental_image_path_label,
            folder=self.experimental_images_folder,
            folder_description="experimental images folder",
            mode_number=experimental_mode,
        )

    def refresh_selected_mode_images(self) -> None:
        if self.results_table.selection():
            self.show_selected_mode_images()

    def display_image(
        self,
        image_path: Optional[Path],
        image_label: tk.Label,
        path_label: tk.Label,
        folder: Optional[Path],
        folder_description: str,
        mode_number: int,
    ) -> Any:
        if folder is None:
            image_label.config(
                image="",
                text=f"Select the {folder_description}.",
            )
            path_label.config(text="")
            return None

        if image_path is None:
            image_label.config(
                image="",
                text=(
                    f"No image found for mode {mode_number}.\n\n"
                    f"Recommended name: mode_{mode_number}.png"
                ),
            )
            path_label.config(text=str(folder))
            return None

        if Image is None or ImageTk is None:
            image_label.config(
                image="",
                text=(
                    "Pillow is not installed.\n\n"
                    "Run:\npython -m pip install -r requirements.txt"
                ),
            )
            path_label.config(text=image_path.name)
            return None

        try:
            with Image.open(image_path) as opened_image:
                image = opened_image.convert("RGB")
                image.thumbnail(
                    self.PREVIEW_SIZE,
                    Image.Resampling.LANCZOS,
                )
                photo = ImageTk.PhotoImage(image.copy())
        except (OSError, ValueError) as error:
            image_label.config(
                image="",
                text=f"Unable to open image:\n{error}",
            )
            path_label.config(text=image_path.name)
            return None

        image_label.config(
            image=photo,
            text="",
        )
        path_label.config(text=image_path.name)
        return photo

    def export_results(self) -> None:
        if not self.comparison_results:
            messagebox.showwarning(
                "No results",
                "Run the frequency comparison first.",
            )
            return

        output_filename = filedialog.asksaveasfilename(
            title="Export comparison results",
            defaultextension=".csv",
            initialfile="modal_comparison_results.csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

        if not output_filename:
            return

        output_path = Path(output_filename)

        try:
            with output_path.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as csv_file:
                writer = csv.writer(csv_file)

                writer.writerow(
                    [
                        "abaqus_mode",
                        "experimental_mode",
                        "abaqus_frequency_hz",
                        "experimental_frequency_hz",
                        "error_percent",
                        "order_changed",
                        "status",
                        "abaqus_image",
                        "experimental_image",
                    ]
                )

                for result in self.comparison_results:
                    abaqus_mode = int(result["abaqus_mode"])
                    experimental_mode = int(
                        result["experimental_mode"]
                    )

                    abaqus_image = find_mode_image(
                        self.abaqus_images_folder,
                        abaqus_mode,
                        "abaqus",
                    )
                    experimental_image = find_mode_image(
                        self.experimental_images_folder,
                        experimental_mode,
                        "experimental",
                    )

                    writer.writerow(
                        [
                            result["abaqus_mode"],
                            result["experimental_mode"],
                            f'{result["abaqus_frequency"]:.6f}',
                            f'{result["experimental_frequency"]:.6f}',
                            f'{result["error_percent"]:.6f}',
                            result["order_changed"],
                            result["status"],
                            str(abaqus_image) if abaqus_image else "",
                            (
                                str(experimental_image)
                                if experimental_image
                                else ""
                            ),
                        ]
                    )

        except OSError as error:
            messagebox.showerror(
                "Export error",
                str(error),
            )
            return

        messagebox.showinfo(
            "Export complete",
            f"Results saved to:\n\n{output_path}",
        )

        self.status_label.config(
            text=f"Results exported: {output_path.name}"
        )


def main() -> None:
    root = tk.Tk()
    ModalComparatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
