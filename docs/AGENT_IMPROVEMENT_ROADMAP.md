# Внутренний roadmap улучшения Abaqus–Simcenter Modal Comparator

**Статус документа:** внутреннее техническое задание для агента  
**Базовая ветка:** `main`  
**Цель:** довести программу до надёжного воспроизводимого инструмента для личной исследовательской работы и последующей реализации задач агентом.

---

## 1. Общие принципы разработки

1. Любое изменение численного алгоритма сначала оформляется воспроизводящим тестом.
2. После каждого изменения MAC, FRF, геометрического mapping или mode pairing выполняется сравнение с текущим эталонным расчётом:
   - полный 121-точечный экспериментальный grid;
   - текущий набор принятых пар;
   - частоты;
   - signed frequency error;
   - MAC;
   - число общих DOF;
   - геометрические параметры.
3. Нельзя одновременно менять алгоритм, пороги принятия и интерфейс отображения результата.
4. Любое изменение, влияющее на численные результаты, увеличивает версию analysis pipeline и инвалидирует старые кэши.
5. Все предупреждения, влияющие на научную интерпретацию, должны быть видимы в GUI, Excel, PDF и metadata.
6. До завершения научного укрепления результаты используются только с явно указанными ограничениями текущего расчётного сценария.

---

# Stage 0 — заморозка исходного состояния

**Приоритет:** P0  
**Цель:** создать контролируемую точку отсчёта перед изменением численного ядра.

## Задачи

- Зафиксировать baseline commit.
- Сохранить эталонный проект с текущим 121-точечным экспериментом.
- Экспортировать:
  - полный список Abaqus и экспериментальных форм;
  - таблицу принятых пар;
  - signed и absolute frequency errors;
  - MAC matrix;
  - AutoMAC;
  - COMAC;
  - geometry mapping distances;
  - перечень предупреждений;
  - manual-review decisions.
- Сохранить хеши входных ODB и UNV/UFF.
- Зафиксировать версии Python, NumPy, SciPy, pyuff, openpyxl, matplotlib и Abaqus.
- Добавить машинно-читаемый baseline JSON.

## Критерий завершения

Повторный запуск на той же версии программы и тех же входных файлах воспроизводит все принятые пары и численные значения в пределах заданного tolerance.

---

# Stage 1 — критическое научное укрепление

**Приоритет:** P0  
**Цель:** устранить ошибки, способные изменить физический смысл MAC и mode pairing.

## 1.1. Индивидуальный measured-DOF mask для каждой формы

### Проблема

Сейчас общий union-маск может использоваться для всех экспериментальных форм.

### Требуемые изменения

- Добавить `measured_dofs` как явное поле `ModeShape`.
- Для каждой экспериментальной формы хранить собственный mask.
- Передавать mode-specific mask через импорт UNV/UFF, geometry mapping, MAC matrix, pair construction, manual review, AutoMAC, COMAC, project persistence и отчёты.
- Не использовать общий union-mask как критерий принятия пары.
- Общий mask разрешить только для диагностических сводок, где это явно указано.

### Тесты

- Разные отсутствующие компоненты у разных форм.
- Разные отсутствующие точки у разных форм.
- Inferred-mask fallback.
- Проверка, что отсутствующий в конкретной форме DOF не входит в её MAC.
- Проверка совместимости со старым project format.

### Критерий завершения

Каждая пара содержит собственный `measured_dof_mask`, а отчёт показывает фактическое число использованных DOF.

---

## 1.2. Minimum common-DOF и coverage gates

### Проблема

MAC может быть рассчитан по одной общей скалярной степени свободы.

### Требуемые изменения

Добавить настраиваемые критерии:

- minimum common DOF count;
- minimum unique point count;
- minimum measured-DOF coverage fraction;
- minimum measurement-point coverage fraction;
- optional minimum spatial extent of accepted points.

Ввести статусы:

- `accepted`;
- `insufficient DOF coverage`;
- `insufficient point coverage`;
- `insufficient spatial coverage`;
- `MAC unavailable`.

Пара с недостаточным покрытием не должна участвовать в автоматическом Hungarian assignment как допустимая.

### Тесты

- Одна общая степень свободы.
- Несколько DOF в одной точке.
- Много точек, но малая пространственная область.
- Полный 121-точечный grid.
- Разные пороги через project settings.

### Критерий завершения

Ни одна автоматически принятая пара не может иметь coverage ниже записанных в отчёте порогов.

---

## 1.3. Geometry-validity mask

### Проблема

Удалённые точки и duplicate FE-node mappings сейчас могут участвовать в MAC.

### Требуемые изменения

- Создать отдельный `geometry_valid_mask`.
- Исключить из принятого MAC точки:
  - за пределами mapping tolerance;
  - с недопустимым residual;
  - повторно отображённые на уже использованный FE-узел, если не применена явная агрегация.
- Для duplicate mappings выбрать один из вариантов:
  1. one-to-one assignment;
  2. documented aggregation;
  3. selection of nearest experimental point.
- Сохранять полный audit trail: accepted/rejected point, distance, mapped FE node и rejection reason.
- Разрешить unfiltered MAC только как диагностическое значение с явной маркировкой.

### Тесты

- Дальний выброс.
- Два experimental points на одном FE node.
- Частичная сетка с несколькими выбросами.
- Полный валидный grid без изменения эталонного результата.

### Критерий завершения

Принятый MAC использует только уникальные геометрически допустимые точки.

---

## 1.4. Надёжное выравнивание частичных и смещённых сеток

### Проблема

Независимое центрирование bounding boxes ненадёжно для половины панели, углового участка и несимметричного grid.

### Требуемые изменения

Поддержать несколько источников transform:

- exact node/point identifiers;
- пользовательские anchor points;
- supplied transform;
- constrained ICP;
- current fast full-grid alignment.

Для каждого решения записывать:

- transform source;
- scale;
- rotation;
- translation;
- determinant/reflection;
- RMS residual;
- inlier fraction;
- ambiguity score;
- number of alternative transforms.

При плохо обусловленной или симметрично неоднозначной геометрии автоматическое принятие должно блокироваться.

### Тесты

- Полный grid.
- Половина панели.
- Один угол.
- Известный поворот и перенос.
- Зеркальная конфигурация.
- Симметричная неоднозначная геометрия.

### Критерий завершения

Программа не принимает частичную сетку без количественного подтверждения качества и однозначности transform.

---

## 1.5. UNV dataset 2420 и локальные системы координат

### Проблема

Локальные системы координат обнаруживаются, но векторы не преобразуются.

### Требуемые изменения

- Разобрать поддерживаемые определения dataset 2420.
- Связать `def_cs` и `disp_cs` с узлами и response directions.
- Преобразовать modal vectors, measurement directions и FRF response directions в единую глобальную систему до вычисления MAC.
- Сохранять оригинальные и преобразованные направления.
- При отсутствующей или неподдерживаемой системе координат завершать импорт явной ошибкой либо блокировать научное принятие MAC.

### Тесты

- Global-only dataset.
- Одна локальная система.
- Несколько локальных систем.
- Отсутствующая ссылка.
- Неподдерживаемый тип системы.
- Эквивалентность global export и local export после преобразования.

### Критерий завершения

MAC для эквивалентных global/local данных совпадает в пределах tolerance.

---

## 1.6. Корректная обработка coherence

### Проблема

Отсутствующая coherence может численно трактоваться как идеальная.

### Требуемые изменения

Ввести явные состояния:

- `computed`;
- `partially_available`;
- `unavailable`;
- `parse_error`.

Правила:

- только `computed` coherence может увеличивать confidence;
- `unavailable` не даёт положительного бонуса;
- `parse_error` вызывает visible warning;
- отсутствие coherence не должно превращаться в значение `1.0` в научных metadata;
- ranking FRF peaks должен разделять amplitude evidence и coherence evidence.

### Тесты

- Полный набор coherence channels.
- Полное отсутствие.
- Частичное отсутствие.
- Malformed scalar fields.
- Несовместимая frequency axis.
- Проверка GUI, reports и cache invalidation.

### Критерий завершения

Ни одна форма без измеренной coherence не маркируется как high-confidence только из-за fallback.

---

## 1.7. Настоящий multi-reference FRF/CMIF

### Проблема

Текущий путь не гарантирует построение response × reference matrix.

### Требуемые изменения

- Идентифицировать канал полным ключом: response node, response direction, reference node, reference direction, physical quantity и frequency axis.
- Не разделять совместимые references на независимые группы.
- На каждой frequency line строить:

  \[
  H(\omega)\in\mathbb{C}^{N_r\times N_f}.
  \]

- Выполнять conventional CMIF/SVD.
- Отдельно хранить singular values, matrix rank, reference count, singular-value ratios, accepted/rejected candidates и confidence.
- Single-reference local snapshot SVD оставить только диагностическим и не повышать его до полноценного multi-reference результата.

### Тесты

- Один reference.
- Два независимых references.
- Дубликат reference.
- Отсутствующий канал.
- Несовместимые frequency axes.
- Две близкие формы с известными shape vectors.
- Проверка, что single-reference candidate не принимается как independent mode автоматически.

### Критерий завершения

На синтетическом двухопорном примере программа восстанавливает ожидаемое число близких форм и корректно сообщает matrix rank.

---

# Stage 2 — модель данных и воспроизводимость

**Приоритет:** P1  
**Цель:** сделать численный результат полностью трассируемым.

## 2.1. Явные dataclass-поля

Добавить в `ModeShape`:

- `measured_dofs`;
- `measurement_directions`;
- `coordinate_system_id`;
- `source_confidence`;
- `source_lineage`.

Добавить в `ModePairResult`:

- `common_dof_mask`;
- `geometry_valid_mask`;
- `common_dof_count`;
- `unique_point_count`;
- `dof_coverage_fraction`;
- `point_coverage_fraction`;
- `spatial_coverage`;
- `acceptance_reasons`;
- `rejection_reasons`;
- `automatic_decision`;
- `manual_decision`.

Убрать критические динамические `setattr`.

## 2.2. Полный run fingerprint

Каждый project, Excel, PDF и metadata JSON должен содержать:

- application version;
- Git commit SHA;
- analysis pipeline version;
- Python и library versions;
- Abaqus version;
- input file paths;
- SHA-256 входных файлов;
- file sizes and timestamps;
- MAC/frequency/coverage thresholds;
- actual masks;
- geometry transform;
- coherence status;
- source lineage;
- manual-review state;
- cache reuse status.

## 2.3. Управление кэшем

- Включить application version и commit SHA в cache key.
- Автоматически инвалидировать cache после изменения numerical pipeline.
- Разделить raw parsed-data, derived-mode, comparison-result и rendered-figure caches.
- Не использовать pickle-файл из неизвестной версии приложения.
- Добавить действие `Clear analysis cache`.

## 2.4. Dependency reproducibility

- Добавить `pyproject.toml`.
- Создать `requirements.in`, lock/constraints file и tested dependency set.
- Зафиксировать совместимые диапазоны, а не только нижние границы.
- Проверять Python version при старте.

---

# Stage 3 — архитектурная консолидация

**Приоритет:** P1  
**Цель:** убрать зависимость программы от порядка monkey patches.

## 3.1. Разделить приложение на явные компоненты

Предлагаемая структура:

- `domain/` — modal models, masks, coverage, lineage;
- `importers/` — Abaqus ODB, UNV/UFF, Polytec;
- `services/` — geometry alignment, MAC, assignment, FRF/CMIF, quality control;
- `reporting/` — Excel, PDF, figures;
- `persistence/` — projects, cache, migrations;
- `ui/` — controllers, views, navigation.

## 3.2. Удаление install-chain

Порядок переноса:

1. reporting;
2. universal reader;
3. comparison core;
4. project/manual review;
5. UI extensions;
6. cache/runtime hardening.

Для каждого вертикального среза:

- сохранить facade временно;
- перенести реализацию в явный компонент;
- подтвердить characterization tests;
- удалить соответствующий `install_*`;
- удалить runtime contract только после завершения переноса.

## 3.3. Dependency injection

GUI должен получать явные services через конструктор, а не импортировать глобально заменённые функции.

### Критерий завершения Stage 3

`main.py` только создаёт зависимости и запускает приложение; численные функции не меняются во время импорта.

---

# Stage 4 — Polytec/Testlab lineage и направления измерения

**Приоритет:** P1 после Stage 1  
**Цель:** корректно представить физический источник данных.

## 4.1. Разделить понятия

Хранить отдельно:

- `experiment_id`;
- `measurement_system`;
- `processing_software`;
- `import_format`;
- `source_display_name`;
- `parent/raw-data lineage`.

Текущий workflow должен отображаться как:

> Abaqus FEM ↔ Polytec experiment processed in Simcenter Testlab.

Не создавать отдельное сравнение `Simcenter ↔ Polytec`, если это два экспорта одного физического эксперимента.

## 4.2. Polytec line-of-sight

- Хранить measurement direction vector для каждой точки.
- Проецировать Abaqus vector на фактическое LOS-направление.
- Поддержать 1D LOS и 3D Polytec export.
- Показывать тип направления в таблице и отчёте.

## 4.3. Опциональный независимый второй эксперимент

Только при наличии второго физически независимого эксперимента включать:

- Abaqus ↔ contact/SCADAS;
- Abaqus ↔ Polytec;
- contact/SCADAS ↔ Polytec;
- three-source summary.

---

# Stage 5 — UI и эксплуатационная готовность

**Приоритет:** P2  
**Цель:** сделать программу удобной для повседневной личной работы без изменения численного ядра.

## Задачи

- Previous/Next navigation для matched modes.
- Единое состояние выбранной пары во всех tabs.
- Responsive comparison table.
- Полные captions и tooltips для coverage/confidence.
- Отдельное отображение accepted, rejected, unresolved и insufficient coverage.
- Кнопка отмены Abaqus extraction.
- Progress stages: ODB extraction, UNV import, geometry, MAC и reporting.
- CLI/batch mode.
- Отдельный `Validate inputs` до запуска полного анализа.
- Экспорт полного пакета воспроизводимости расчёта.
- Диагностика совместимости текущих версий Abaqus, Python и pyuff.
- Clear cache.
- Safe project migration.

---

# Stage 6 — тестирование на реальных данных

**Приоритет:** P0 перед использованием на новых типах данных  
**Цель:** доказать переносимость за пределами одного текущего файла.

## Минимальная матрица реальных тестов

### Abaqus

- минимум две версии Abaqus;
- real eigenvalue modes;
- complex modes;
- несколько instances;
- shell и solid models;
- разные mode ranges.

### UNV/UFF

- dataset 55;
- dataset 2414;
- dataset 58 single-reference;
- dataset 58 multi-reference;
- dataset 2420;
- неполный grid;
- разные pyuff variants.

### Геометрия

- полный grid;
- половина панели;
- угловой grid;
- mirrored axes;
- mm ↔ m scale;
- duplicate points;
- outliers.

### Эксперимент

- Polytec LOS;
- Polytec 3D;
- contact accelerometers;
- два независимых эксперимента.

## Требуемые артефакты

- anonymized fixtures или fixture generator;
- expected result JSON;
- tolerance specification;
- regression report;
- список проверенных сочетаний версий и форматов.

---
