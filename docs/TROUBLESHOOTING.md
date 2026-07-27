# Troubleshooting

## `The truth value of an array with more than one element is ambiguous`

This was caused by Abaqus exposing `FieldValue.data` or `conjugateData` as an array. Version 1.0.1 and later convert these values explicitly to lists and never test an array as a Boolean value.

After updating the repository, rerun the same ODB and UNV files. Existing incomplete extraction folders can remain; the extractor overwrites the mode CSV files and creates `manifest.json` after a successful run.
