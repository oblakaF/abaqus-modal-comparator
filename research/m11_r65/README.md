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
| `cmac_research.py` | Pure functions: complex MAC, subspace projection, point ordering, candidates A–D, scenario geometry, nearest-node and S4R bilinear transfer, identity verification. It also holds `PROTOCOL`, the scenarios and methods declared before any experimental–FE MAC was computed (`protocol_sha256()`). |
| `run_m11_r65.py` | The runner on the verified M11 copies. Input paths come from a JSON file kept **outside Git**. Every input is refused unless its SHA-256 equals `expected_inputs.json`. It writes only to `--out`. |
| `expected_inputs.json` | SHA-256 of the verified inputs (names only, no paths). |
| `test_cmac_research.py` | Synthetic tests only; no real data. |

Run the synthetic tests (not part of the `tests/` CI suite):

```
python -m unittest discover -s research/m11_r65 -v
```

Run on the real copies. Neither the data nor the outputs are committed:

```
python research/m11_r65/run_m11_r65.py --config <inputs.json outside Git> --out <work directory>
```

The FE connectivity is taken from the verified INP copy. That is a research hypothesis: the INP–ODB identity is
`NODES_AND_INP_CONTENT`, not proven mesh identity.
