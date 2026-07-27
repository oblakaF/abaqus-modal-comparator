# ODB and UNV workflow

1. Open the application with `RUN_PROGRAM.cmd`.
2. Select the Abaqus ODB.
3. Select the Simcenter Testlab UNV/UFF file.
4. Confirm the Abaqus command and modes 6–14.
5. Run the analysis.
6. Review the comparison table, mode shapes, MAC matrix, and details tabs.
7. Export Excel and PDF reports.

The first real-file run is the compatibility test for the exact Abaqus and Testlab versions used in the laboratory. If a source-file variant is not recognized, the program writes `last_error.log` in the output workspace.
