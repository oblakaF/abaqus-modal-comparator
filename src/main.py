from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox


class ModalComparatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Abaqus Modal Comparator")
        self.root.geometry("720x430")
        self.root.minsize(650, 400)

        self.abaqus_file: Path | None = None
        self.experimental_file: Path | None = None
        self.images_folder: Path | None = None

        title = tk.Label(
            root,
            text="Abaqus Modal Comparator",
            font=("Arial", 20, "bold"),
        )
        title.pack(pady=(25, 5))

        subtitle = tk.Label(
            root,
            text="Сравнение расчётных и экспериментальных мод",
            font=("Arial", 11),
        )
        subtitle.pack(pady=(0, 25))

        frame = tk.Frame(root)
        frame.pack(fill="x", padx=40)

        self.abaqus_label = self.create_file_row(
            frame,
            row=0,
            button_text="Выбрать данные Abaqus",
            command=self.select_abaqus_file,
        )

        self.experimental_label = self.create_file_row(
            frame,
            row=1,
            button_text="Выбрать частоты эксперимента",
            command=self.select_experimental_file,
        )

        self.images_label = self.create_file_row(
            frame,
            row=2,
            button_text="Выбрать папку изображений",
            command=self.select_images_folder,
        )

        check_button = tk.Button(
            root,
            text="Проверить выбранные данные",
            command=self.check_inputs,
            width=32,
            height=2,
        )
        check_button.pack(pady=30)

        self.status_label = tk.Label(
            root,
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
            width=31,
        )
        button.grid(row=row, column=0, padx=(0, 15), pady=10)

        label = tk.Label(
            parent,
            text="Не выбрано",
            anchor="w",
            width=48,
        )
        label.grid(row=row, column=1, sticky="w")

        return label

    def select_abaqus_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Выберите файл с данными Abaqus",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            self.abaqus_file = Path(filename)
            self.abaqus_label.config(text=self.abaqus_file.name)
            self.status_label.config(text="Выбран файл Abaqus")

    def select_experimental_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Выберите файл экспериментальных частот",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            self.experimental_file = Path(filename)
            self.experimental_label.config(text=self.experimental_file.name)
            self.status_label.config(text="Выбран файл эксперимента")

    def select_images_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Выберите папку с изображениями экспериментальных мод"
        )

        if folder:
            self.images_folder = Path(folder)
            self.images_label.config(text=self.images_folder.name)
            self.status_label.config(text="Выбрана папка изображений")

    def check_inputs(self) -> None:
        missing = []

        if self.abaqus_file is None:
            missing.append("данные Abaqus")

        if self.experimental_file is None:
            missing.append("частоты эксперимента")

        if self.images_folder is None:
            missing.append("папка изображений")

        if missing:
            messagebox.showwarning(
                "Данные выбраны не полностью",
                "Не выбраны:\n\n" + "\n".join(missing),
            )
            return

        messagebox.showinfo(
            "Проверка завершена",
            "Все необходимые данные выбраны.",
        )
        self.status_label.config(text="Все входные данные выбраны")


def main() -> None:
    root = tk.Tk()
    ModalComparatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()