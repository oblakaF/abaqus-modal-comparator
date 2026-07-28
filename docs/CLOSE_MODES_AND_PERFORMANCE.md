# Close-mode separation and performance

## Why the first run can be slow

The first analysis has several expensive stages:

1. Abaqus starts its own Python interpreter and reads the proprietary ODB.
2. Every selected modal vector is exported from the FE mesh.
3. The UNV reader parses hundreds of dataset-58 channels and all frequency lines.
4. Experimental points are aligned to the FE mesh and MAC is evaluated for candidate orientations.
5. Diagnostic figures are rendered.

For a large FE mesh, the ODB extraction and conversion of text CSV modal vectors are normally the dominant costs.

## Repeat-run acceleration

The application now maintains two reusable binary caches:

- a binary Abaqus modal dataset beside the extracted ODB manifest;
- a parsed UNV modal dataset under the current user's local application cache.

The cache key includes source path, size, modification time, selected Abaqus frequencies, requested peak count, and algorithm version. Editing or replacing either source file invalidates the corresponding cache automatically.

On a repeated analysis with unchanged files, the program should report:

```text
ODB extraction reused: True
Binary ODB dataset reused: True
UNV cache reused: disk or memory
```

The first run after a program update that changes the cache algorithm rebuilds the cache once.

## Close modes

A conventional peak-pick can return one experimental shape when two numerical modes lie inside one overlapping resonance band. The program now detects close Abaqus-frequency clusters and evaluates the complex response matrix in a local band.

### Multiple excitation references

When multiple independent references are available, the method is compatible with a conventional CMIF interpretation based on singular values of the frequency-response matrix.

### One excitation reference

The supplied panel UNV has one excitation reference. A true multi-reference CMIF cannot produce more than one non-zero singular value at each individual frequency line. The program therefore uses local response-matrix SVD across the frequency lines inside the overlapping band.

This method can identify an additional independent spatial component, but it is model-assisted screening rather than a replacement for a full Simcenter modal curve fit. An added split mode must still satisfy:

- frequency proximity;
- MAC threshold;
- AutoMAC distinguishability;
- acceptable coherence;
- visual agreement of the mode shape.

The `Close modes — SVD` tab shows the local component-energy curves, added candidate frequencies, singular-value ratios, cache status, and load times.
