import csv
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple


FrequencyRow = Tuple[int, float]
ComparisonRow = Dict[str, object]


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
            raise ValueError("В CSV-файле отсутствует строка заголовков.")

        normalized_fields = {
            field.strip().lower(): field
            for field in reader.fieldnames
            if field is not None
        }

        if "mode" not in normalized_fields:
            raise ValueError(
                "В CSV-файле отсутствует столбец 'mode'."
            )

        if "frequency_hz" not in normalized_fields:
            raise ValueError(
                "В CSV-файле отсутствует столбец 'frequency_hz'."
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
                    f"Ошибка в строке {line_number}: "
                    f"mode='{mode_text}', frequency_hz='{frequency_text}'."
                ) from error

            if frequency <= 0:
                raise ValueError(
                    f"В строке {line_number} частота должна быть больше нуля."
                )

            rows.append((mode, frequency))

    if not rows:
        raise ValueError("В CSV-файле не найдено ни одной моды.")

    rows.sort(key=lambda item: item[0])
    return rows


def frequency_error(
    abaqus_frequency: float,
    experimental_frequency: float,
) -> float:
    """
    Calculate relative frequency difference in percent.

    Experimental frequency is used as the reference.
    """
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
    Find a one-to-one mode matching with minimum total frequency error.

    The algorithm checks all valid assignments using dynamic programming.
    It is well suited for the planned set of nine modes.
    """
    if not abaqus_rows:
        raise ValueError("Список мод Abaqus пуст.")

    if not experimental_rows:
        raise ValueError("Список экспериментальных мод пуст.")

    # The smaller list is used as the row set.
    # Each row is assigned to one unique item from the larger list.
    rows_are_abaqus = len(abaqus_rows) <= len(experimental_rows)

    if rows_are_abaqus:
        small_rows = abaqus_rows
        large_rows = experimental_rows
    else:
        small_rows = experimental_rows
        large_rows = abaqus_rows

    if len(large_rows) > 18:
        raise ValueError(
            "Для первой версии допускается не более 18 мод в одном файле."
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

            small_mode, small_frequency = small_rows[row_index]
            large_mode, large_frequency = large_rows[column_index]

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
            status = "Совпадает"
        elif error_percent <= 10.0:
            status = "Проверить"
        else:
            status = "Сильное расхождение"

        results.append(
            {
                "abaqus_mode": abaqus_mode,
                "experimental_mode": experimental_mode,
                "abaqus_frequency": abaqus_frequency,
                "experimental_frequency": experimental_frequency,
                "error_percent": error_percent,
                "order_changed": "Да" if order_changed else "Нет",
                "status": status,
            }
        )

    return results


class ModalComparatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Abaqus Modal Comparator")
        self.root.geometry("1120x690")
        self.root.minsize(950, 600)

        self.abaqus_file: Optional[Path] = None
        self.experimental_file: Optional[Path] = None
        self.images_folder: Optional[Path] = None
        self.comparison_results: List[ComparisonRow] = []

        self.build_interface()

    def build_interface(self) -> None:
        title = tk.Label(
            self.root,
            text="Abaqus Modal Comparator",
            font=("Arial", 20, "bold"),
        )
        title.pack(pady=(18, 3))

        subtitle = tk.Label(
            self.root,
            text="Сравнение расчётных и экспериментальных частот",
            font=("Arial", 11),
        )
        subtitle.pack(pady=(0, 15))

        input_frame = ttk.LabelFrame(
            self.root,
            text="Исходные данные",
            padding=12,
        )
        input_frame.pack(fill="x", padx=20, pady=5)

        self.abaqus_label = self.create_file_row(
            input_frame,
            row=0,
            button_text="Выбрать CSV Abaqus",
            command=self.select_abaqus_file,
        )

        self.experimental_label = self.create_file_row(
            input_frame,
            row=1,
            button_text="Выбрать CSV эксперимента",
            command=self.select_experimental_file,
        )

        self.images_label = self.create_file_row(
            input_frame,
            row=2,
            button_text="Выбрать папку изображений",
            command=self.select_images_folder,
        )

        buttons_frame = tk.Frame(self.root)
        buttons_frame.pack(pady=12)

        compare_button = tk.Button(
            buttons_frame,
            text="Сравнить частоты",
            command=self.compare_frequencies,
            width=25,
            height=2,
        )
        compare_button.pack(side="left", padx=8)

        self.export_button = tk.Button(
            buttons_frame,
            text="Сохранить результат CSV",
            command=self.export_results,
            width=25,
            height=2,
            state="disabled",
        )
        self.export_button.pack(side="left", padx=8)

        table_frame = ttk.LabelFrame(
            self.root,
            text="Результаты сопоставления",
            padding=8,
        )
        table_frame.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=(0, 10),
        )

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
            table_frame,
            columns=columns,
            show="headings",
            height=12,
        )

        self.results_table.heading(
            "abaqus_mode",
            text="Мода Abaqus",
        )
        self.results_table.heading(
            "experimental_mode",
            text="Мода эксперимента",
        )
        self.results_table.heading(
            "abaqus_frequency",
            text="Abaqus, Hz",
        )
        self.results_table.heading(
            "experimental_frequency",
            text="Эксперимент, Hz",
        )
        self.results_table.heading(
            "error_percent",
            text="Ошибка, %",
        )
        self.results_table.heading(
            "order_changed",
            text="Порядок изменён",
        )
        self.results_table.heading(
            "status",
            text="Результат",
        )

        self.results_table.column(
            "abaqus_mode",
            width=105,
            anchor="center",
        )
        self.results_table.column(
            "experimental_mode",
            width=145,
            anchor="center",
        )
        self.results_table.column(
            "abaqus_frequency",
            width=120,
            anchor="center",
        )
        self.results_table.column(
            "experimental_frequency",
            width=145,
            anchor="center",
        )
        self.results_table.column(
            "error_percent",
            width=105,
            anchor="center",
        )
        self.results_table.column(
            "order_changed",
            width=130,
            anchor="center",
        )
        self.results_table.column(
            "status",
            width=160,
            anchor="center",
        )

        vertical_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.results_table.yview,
        )
        self.results_table.configure(
            yscrollcommand=vertical_scrollbar.set
        )

        self.results_table.pack(
            side="left",
            fill="both",
            expand=True,
        )
        vertical_scrollbar.pack(
            side="right",
            fill="y",
        )

        self.summary_label = tk.Label(
            self.root,
            text="Результаты ещё не рассчитаны",
            font=("Arial", 10, "bold"),
        )
        self.summary_label.pack(pady=(0, 8))

        self.status_label = tk.Label(
            self.root,
            text="Программа готова к работе",
            anchor="w",
            relief="sunken",
            padx=10,
        )
        self.status_label.pack(side="bottom", fill="x")

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
            width=29,
        )
        button.grid(
            row=row,
            column=0,
            padx=(0, 12),
            pady=6,
        )

        label = tk.Label(
            parent,
            text="Не выбрано",
            anchor="w",
        )
        label.grid(
            row=row,
            column=1,
            sticky="w",
        )

        parent.grid_columnconfigure(1, weight=1)
        return label

    def select_abaqus_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Выберите CSV-файл Abaqus",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            self.abaqus_file = Path(filename)
            self.abaqus_label.config(
                text=str(self.abaqus_file)
            )
            self.status_label.config(
                text="Выбран файл с частотами Abaqus"
            )

    def select_experimental_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Выберите CSV-файл эксперимента",
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
                text="Выбран файл экспериментальных частот"
            )

    def select_images_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Выберите папку с изображениями мод"
        )

        if folder:
            self.images_folder = Path(folder)
            self.images_label.config(
                text=str(self.images_folder)
            )
            self.status_label.config(
                text=(
                    "Папка изображений выбрана. "
                    "Изображения будут добавлены позднее."
                )
            )

    def clear_table(self) -> None:
        for item_id in self.results_table.get_children():
            self.results_table.delete(item_id)

    def compare_frequencies(self) -> None:
        if self.abaqus_file is None:
            messagebox.showwarning(
                "Не выбран файл",
                "Выберите CSV-файл с частотами Abaqus.",
            )
            return

        if self.experimental_file is None:
            messagebox.showwarning(
                "Не выбран файл",
                "Выберите CSV-файл с экспериментальными частотами.",
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
                "Ошибка чтения данных",
                str(error),
            )
            self.status_label.config(
                text="Не удалось выполнить сравнение"
            )
            return

        self.clear_table()

        for result in self.comparison_results:
            self.results_table.insert(
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
                f"Сопоставлено мод: "
                f"{len(self.comparison_results)} | "
                f"Средняя ошибка: {average_error:.2f}% | "
                f"Максимальная ошибка: {maximum_error:.2f}%"
            )
        )

        self.export_button.config(state="normal")
        self.status_label.config(
            text="Сравнение частот успешно завершено"
        )

    def export_results(self) -> None:
        if not self.comparison_results:
            messagebox.showwarning(
                "Нет результатов",
                "Сначала выполните сравнение частот.",
            )
            return

        output_filename = filedialog.asksaveasfilename(
            title="Сохранить результаты сравнения",
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
                    ]
                )

                for result in self.comparison_results:
                    writer.writerow(
                        [
                            result["abaqus_mode"],
                            result["experimental_mode"],
                            f'{result["abaqus_frequency"]:.6f}',
                            f'{result["experimental_frequency"]:.6f}',
                            f'{result["error_percent"]:.6f}',
                            result["order_changed"],
                            result["status"],
                        ]
                    )

        except OSError as error:
            messagebox.showerror(
                "Ошибка сохранения",
                str(error),
            )
            return

        messagebox.showinfo(
            "Файл сохранён",
            f"Результаты сохранены:\n\n{output_path}",
        )

        self.status_label.config(
            text=f"Результаты сохранены: {output_path.name}"
        )


def main() -> None:
    root = tk.Tk()
    ModalComparatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()