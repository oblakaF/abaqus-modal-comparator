# M11 R6.5 — research-only experimental–FE complex MAC

**Status of every result:**

- `RESEARCH_DIAGNOSTIC_ONLY`
- `COMPUTATIONAL_CONVENTION_ONLY`
- `NO_ACCEPTED_PHYSICAL_REGISTRATION`

This directory is isolated from the application. It is not the production comparator and creates no
`FrozenRegistration`, no `corner_A_marker` and no `panel_edges` evidence. It applies no pairing criterion. Nothing
here feeds Auto-ID, LM or material constants. SPEC v1.2, the governed schemas, the R7 gate and the thresholds are
unchanged.

| File | Content |
|---|---|
| `cmac_research.py` | Pure functions: complex MAC, subspace projection, point ordering, candidates A–D, scenario geometry, nearest-node and S4R bilinear transfer, and the fail-closed location policy `PathPolicy` with identity verification. It also holds `PROTOCOL`, the scenarios and methods fixed before the first experimental–FE MAC (`protocol_sha256()`). The protocol's SHA and time were recorded in a local execution log only, so it is **not** an independently verified preregistration. |
| `run_m11_r65.py` | The runner on the verified M11 copies. Input paths come from a JSON file kept **outside Git**. **Location is checked first**, before any read or hash: inputs and config must come from the declared input roots, never from an original store, through a link or junction, or as a hard link. Only then is the SHA-256 compared with `expected_inputs.json`. Output is allowed only inside `--output-root`, never in protected roots or the repository. |
| `expected_inputs.json` | SHA-256 of the verified inputs (names only, no paths). |
| `test_cmac_research.py` | Synthetic tests only; no real data. |

Run the synthetic tests. They also run in CI as a separate step of `.github/workflows/tests.yml`:

```
python -m unittest discover -s research/m11_r65 -v
```

Run on the real copies. Neither the data nor the outputs are committed:

```
python research/m11_r65/run_m11_r65.py --config <inputs.json> --out <output-root>/<run> \
    --input-root <verified copy root> --input-root <derived work root> \
    --protected-root <verified copy root> --output-root <output-root>
```

The FE connectivity is taken from the verified INP copy. That is a research hypothesis: the INP–ODB identity is
`NODES_AND_INP_CONTENT`, not proven mesh identity.
