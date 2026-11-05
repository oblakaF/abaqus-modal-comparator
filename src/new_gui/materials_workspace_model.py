"""GUI-UX-R1: the facts the Materials page can state about two chosen files, with no Qt.

Read-only: the study section beside it (MAT-3) never uses these files. The FE facts come from an already extracted package (its manifest and geometry file; the mode files are not read
and Abaqus is never started). The extraction stores no material, section, layup, density, thickness or length unit, so none
of them is shown or guessed. Nothing here computes a material value, runs an iteration or starts a solver.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

from new_gui import analyze_model as am
from new_gui import preview_model as pm
from new_gui.workspace_state import EXPERIMENTAL
from services import odb_import_service as svc

NOT_STORED = "Нет в извлечённых данных"
NO_PACKAGE = ("Для этого ODB не найдены извлечённые моды, поэтому геометрия не показана. Сначала выполните Analyze для этого ODB. "
              "Эта страница никогда не запускает Abaqus.")
MATERIAL_STATEMENT = ("В извлечённых данных FE нет названий материалов, сечений, укладок, E1, E2, G12, плотности, толщины и "
                      "единиц, и программа их не угадывает. Чтобы их показать, нужен отдельный источник INP или CAE либо расширенное "
                      "извлечение из ODB через Abaqus Python с отдельным разрешением.")
PROPERTY_HEADERS = ("Свойство", "Вход FE", "Независимое измерение", "Идентифицировано / откалибровано")
INPUT_PROPERTIES = ("Названия материалов", "Сечения и укладки", "E1, E2, G12", "Плотность", "Толщина", "Единица длины")
NOT_PROVIDED, NOT_ISSUED = "Не предоставлено", "Не выдано"
WORKFLOW = ("1. Загрузить FE-модель образца и экспериментальный модальный набор.",
            "2. Проверить фактические входные свойства и геометрию.",
            "3. Выбрать научно утверждённый набор параметров калибровки.",
            "4. Установить физическую регистрацию и идентичность мод.",
            "5. Выполнить явно разрешённые итерации FE.",
            "6. Оценить невязки частот, результаты HOLDOUT, неопределённость и чувствительность к форме модели.",
            "7. Сообщить обоснованный результат либо научный отказ.")
WORKFLOW_TITLE = "Калибровка модели одной плиты: будущий рабочий процесс, сейчас недоступен"
STATUS_TEXT = ("Текущий научный статус: на реальных файлах эта страница не запускает оптимизатор, итерации FE или решатель и не выдаёт "
               "чисел. Вкладка «Расчёт» выполняет только синтетические проверки программы. Совпадение частот не устанавливает значение материала. Калибровка для конкретной модели не является идентифицированным "
               "свойством материала.")


def property_rows() -> tuple:
    return tuple((name, NOT_STORED, NOT_PROVIDED, NOT_ISSUED) for name in INPUT_PROPERTIES)


@dataclass(frozen=True)
class Facts:
    rows: tuple  # (caption, value)
    note: str = ""
    shapes: str = ""  # experimental: whether the records hold shapes; "" when not known from this source
    data_kind: str = ""  # experimental: fitted modes, FRF peaks or UNKNOWN; "" when not known from this source


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def geometry_facts(manifest: Path, cancel_event=None) -> tuple:
    """Node count, instances and extents from the package's geometry file, streamed; the mode files are not opened."""
    document = json.loads(Path(manifest).read_text(encoding="utf-8"))
    path = Path(manifest).parent / document["geometry_file"]
    low, high = [math.inf] * 3, [-math.inf] * 3
    instances, count = set(), 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            count += 1
            if cancel_event is not None and count % 65536 == 0 and cancel_event.is_set():
                raise am.StepCancelled()
            instances.add(row.get("instance") or "")
            for axis, key in enumerate("xyz"):
                value = float(row[key])
                low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
    rows = [("Извлечённые моды", f"{document.get('start_mode', '?')} – {document.get('end_mode', '?')}"),
            ("Шаг", str(document.get("step_name") or "не записан")),
            ("Название анализа", str(document.get("analysis_title") or "не записано")),
            ("Узлы", str(count)), ("Экземпляры", ", ".join(sorted(i for i in instances if i)) or "не записаны")]
    if count:
        rows += [(f"Диапазон {key}", f"{_fmt(low[axis])} – {_fmt(high[axis])} (размер {_fmt(high[axis] - low[axis])})")
                 for axis, key in enumerate("XYZ")]
    rows.append(("Единицы", "В извлечённых данных не указаны"))
    return tuple(rows)


def source_rows(odb: Path, package_found: bool) -> tuple:
    """Whether the extracted data and a model source exist. Files beside the ODB are named only; they are not opened."""
    rows = [("Пакет FE", "Найден: извлечённые моды содержимого этого ODB" if package_found else "Не найден")]
    for suffix, caption in ((".inp", "INP"), (".cae", "CAE")):
        candidate = odb.with_suffix(suffix)
        rows.append((f"{caption} рядом с ODB", f"{candidate.name} есть, но не разбирался" if candidate.is_file() else "Не найден"))
    return tuple(rows)


def read_fe_facts(odb, cancel_event, say=None) -> Facts:
    """Find the package of this ODB's content (hashing it, as Analyze does) and state its geometry. Starts no process."""
    odb = Path(odb)
    try:
        identity = svc.hash_file(odb, cancel_event, say)
        folder = am.package_folder(odb)
        found = (svc.existing_packages(folder, identity["sha256"], am.FIRST_MODE, am.LAST_MODE)
                 or svc.existing_packages(folder, identity["sha256"], am.FIRST_MODE, am.LAST_MODE, covering=True))
    except svc.OdbImportCancelled as error:
        raise am.StepCancelled() from error
    except (svc.OdbImportRefused, OSError) as error:
        raise am.StepFailed(f"The ODB could not be read: {error}") from error
    if not found:
        return Facts(source_rows(odb, False), NO_PACKAGE)
    return Facts(source_rows(odb, True) + geometry_facts(found[0] / "manifest.json", cancel_event))


def experimental_facts(preview) -> Facts:
    rows = [("Файл", Path(preview.selected_path).name), ("Типы наборов данных", ", ".join(str(x) for x in preview.dataset_types) or "нет"),
            ("Узлы геометрии", str(preview.geometry_node_count)), ("Модальные наборы", str(len(preview.sets)))]
    for item in preview.sets:
        points = max((record.point_count for record in item.records), default=0)
        dofs = max((record.measured_dof_count for record in item.records), default=0)
        peak = any(record.provisional for record in item.records)
        rows.append((item.title, f"точек: {points}, измеренных степеней свободы: {dofs}" + ("; пик FRF — не подобранная мода" if peak else "")))
    rows.append(("Единицы", "В прочитанных данных не указаны"))
    records = [record for item in preview.sets for record in item.records]
    shaped = sum(1 for record in records if record.point_count > 0)
    shapes = f"Есть: {shaped} из {len(records)} записей" if shaped else "Нет"
    return Facts(tuple(rows), shapes=shapes, data_kind=_data_kind(records))


def _data_kind(records) -> str:
    """As the importer classified the records. A file's name or title is not evidence of what it holds."""
    if records and all(record.provisional for record in records):
        return "Пики FRF: не подобранные моды"
    if records and all(not record.provisional and str(record.classification).startswith("FITTED") for record in records):
        return "Подобранные моды"
    return "UNKNOWN"


def read_experimental_facts(path, cancel_event) -> Facts:
    outcome = pm.run_read(EXPERIMENTAL, path, 0, cancel_event)
    if outcome.cancelled or cancel_event.is_set():
        raise am.StepCancelled()
    if outcome.error:
        raise am.StepFailed(outcome.error)
    return experimental_facts(outcome.preview)


def saved_facts(document: dict) -> tuple:
    """From a saved result's own file: no path named in it is looked at."""
    fe_modes, modes = document["modes"]["fe"], document["modes"]["experimental"]
    fe = Facts((("Извлечённые моды при сохранении", f"{len(fe_modes)}"), ("Единицы", "В извлечённых данных не указаны")),
               "Из сохранённого файла. Исходные файлы не открывались.")
    experimental = Facts((("Модальный набор при сохранении", document["modal_set"]["title"]), ("Записи при сохранении", str(len(modes)))),
                         "Из сохранённого файла. Исходные файлы не открывались.")
    return fe, experimental


__all__ = ["Facts", "source_rows", "MATERIAL_STATEMENT", "PROPERTY_HEADERS", "STATUS_TEXT", "WORKFLOW", "WORKFLOW_TITLE", "experimental_facts",
           "geometry_facts", "property_rows", "read_experimental_facts", "read_fe_facts", "saved_facts"]
