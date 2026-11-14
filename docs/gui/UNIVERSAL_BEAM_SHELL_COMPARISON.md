# Two-file comparison on a beam and on a curved shell

**Status: REVIEW_READY.** Branch `feature/materials-offline-v1`, from `11acbcf`. Verified on synthetic data only; nothing
here is a physical validation.

The Analyze page compares an `.odb` and a `.unv` / `.uff` through the same services for every geometry. This note
covers what a beam and a tube need in **Set up registration...**, and what the result then says for each mode.

## What to state

| Case | Measured side | Measured DOFs | Sensor directions |
|---|---|---|---|
| Flat plate, one face | the FE direction the face looks towards | the measured component | leave empty |
| Beam, sensors along one axis | the FE direction the sensors face | the measured component | leave empty |
| Tube or closed section, three components per point | **all around the part** | x, y, z as measured | leave empty |
| Tube, one radial sensor per point | **all around the part** | the components the radial vectors have | one line per point |

- **All around the part** means no single face is stated. Each point takes its nearest FE node of the measured part.
- **Sensor directions** are for single-axis sensors that do not all measure along one experimental axis. Write
  `point, dx, dy, dz` in experimental axes for every point. FE motion is then compared along these directions: the FE
  displacement of each mapped node is projected on its point's direction before MAC is computed.
- **A scan the other way round** (a beam measured from the far end, a sensor facing the other way) is stated by the
  axes, for example `+x → -X`, `+z → -Z`, and by landmarks that pair each end with the end it really is.
- **Landmarks on a tube** fix the angular position; the geometry alone fits any turn about the axis. Give a landmark
  as the FE position of the sensor on the measured surface when the FE nodes lie on another surface (mid-surface).

## What is refused

No MAC is computed, and the reason is displayed, when:

- the file's vectors show single-axis sensors in different directions and no direction is stated
  (`MEASUREMENT_DIRECTION_REQUIRED`);
- the file's vectors do not lie along the stated directions, or the points hold more than one direction
  (`MEASUREMENT_DIRECTION_CONTRADICTED`);
- the directions are incomplete, unreadable or use a component that is not a stated measured DOF (`SENSOR_DIRECTION`);
- a point lies equally near two FE nodes that follow one another along its sensor direction, so the measured surface
  is unknown (`SURFACE_OFFSET_UNKNOWN`);
- the landmarks contradict the stated axes, lie on one line without stated axes, or mirror the model.

A file that stores each sensor's reading in one column without its direction cannot be compared.

## Verdict of each mode

The **Nearest frequency** table has a *Verdict* for every experimental record, and the **Mode pairs** table for every
pair. The words restate the comparator's own result; no pair or limit is added.

| Verdict | Meaning |
|---|---|
| `CORRESPONDENCE_CONFIRMED` | one admissible FE mode, assigned, comparator status Excellent or Good |
| `CORRESPONDENCE_AMBIGUOUS` | several admissible candidates, a weaker status, or a pair without MAC |
| `CORRESPONDENCE_REJECTED` | no FE mode passes the comparator's limits |
| `INSUFFICIENT_REGISTRATION_EVIDENCE` | no verified or confirmed registration, so no MAC |

A verdict holds for the registration that was confirmed.

## Limits

- A statement that is wrong but fits the geometry is not detected by the registration. On a tube turned about its axis
  by a wrong angle the comparison still runs; the tests show the bending pair is then not confirmed, but a turn that
  maps one shape of a degenerate pair onto the other would be.
- The geometry tolerance is 3 % of the scan diagonal. On a slender tube it can exceed the spacing of sensors around the
  circumference, and four landmarks around a long tube can fall under the 5 % landmark-extent rule; state the axes then.
- Sensor directions are typed per point; there is no rule such as "normal to the surface".
- With one record in the file, sensors in different directions cannot be recognised without a statement.
- Local coordinate systems in the UNV (dataset 2420) are still refused.
- The confirmation's statements are unchanged; the sensor directions are displayed among its checks.

## Code

- `src/services/generic_registration.py`: the `AROUND` side, `sensor_directions`, the surface offset.
- `src/new_gui/comparison_model.py`: the direction checks, the projection, `mode_verdicts`.
- `src/new_gui/analyze_model.py`, `src/new_gui/registration_dialog.py`: the form and the verdict columns.
- `tests/test_universal_geom_beam_shell.py`.
