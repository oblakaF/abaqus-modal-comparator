# UNIVERSAL-REG-3: confirmed physical registration

Technical note for reviewers of the two-file workflow on the Analyze page.

## Workflow

1. Choose an `.odb` and a `.unv` / `.uff`, then click Analyze. The result is `REGISTRATION_REQUIRED` with frequency-only
   diagnostics.
2. **Set up registration...**: state the units, axes, measured side, measured DOFs, landmarks and evidence source.
3. **Check evidence**, tick the review, **Save draft...** (a diagnostic file, never an acceptance).
4. **Confirm registration...** revalidates the saved draft now. Only then does a separate dialog display every value and
   the point mapping, and ask for each physical statement, the person's name and where the evidence is kept. The
   confirmation goes to its own file.
5. **Compare with confirmed registration** runs the existing comparator. **Open confirmation...** reuses a saved file
   after a new analysis; it is displayed and used only on command.

## What guards the comparator

`comparison_model.compare_confirmed` takes the confirmation's content, not a registration object. Before every
comparison it:

- refuses FRF peak (provisional) records;
- identifies the experimental file and the FE package again, against what was read;
- checks the confirmation's schema, fields, SHA-256 and non-claims (`governed`, `production_ready` and
  `independent_verification` must be false);
- revalidates the embedded draft on the current data: source hashes, modal set, both geometries, and the whole result
  computed again from the stored evidence;
- builds the `FrozenRegistration` again and requires the confirmed `registration_hash`, then `check_content_compatible`.

The comparison runs on the first-20-mode subsets. Archived registrations are not consulted on this route, so there is no
fallback. Any refusal leaves `REGISTRATION_REQUIRED` and the frequency-only result.

## Geometry convention

The draft states `x_fe = (s x_exp) R^T + t` in row vectors. The comparator's frozen geometry is
`x_exp = (x_fe R') s' + t'`, so `R' = R`, `s' = 1 / s` and `t' = -(t R) / s`. Tests check this through the comparator's
own `geometry.distances` and a measured direction along another FE axis.

## What a confirmation is not

A confirmation records a named person's statement. It is not proof of physical correctness, independent verification or
governed evidence, and it adds no Auto-ID observation. The name is typed, not authenticated, and landmark independence
cannot be checked by software. The result status is `USER_CONFIRMED_COMPARISON`, not `VERIFIED_COMPARISON`. The 5 %, 5
degree and 1 % rules stay provisional diagnostic heuristics, and a confirmation cannot change that.

## Known limits

- Orientation is never chosen by the program, so wrong statements that are geometrically consistent are not detected. On
  a symmetric plate, the geometry fits several orientations and only the stated evidence separates them.
- The shapes shown for a pair are each on their own coordinates. No overlay on the registered points is offered here.
- Re-extracting the same ODB can change the package hash, and the confirmation then no longer holds.
- A measured-DOF mask must be explicit and uniform across records, as the registration factory already requires.
