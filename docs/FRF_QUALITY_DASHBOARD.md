# FRF and quality-control dashboard

The application now includes a dedicated **FRF & quality** tab.

It displays:

- the combined experimental FRF indicator;
- mean coherence across measurement channels;
- every detected resonance candidate;
- the experimental peaks accepted in Abaqus mode pairs;
- matched Abaqus frequencies;
- a reduced MAC matrix containing verified pairs only;
- excluded near-zero rigid modes;
- unmatched Abaqus modes;
- unmatched experimental peak candidates;
- closely spaced mode groups that may appear as mixed experimental shapes.

The Testlab FRF peak detector now receives the selected Abaqus frequencies as search targets. These targets guide candidate ranking but do not replace FRF peak detection or MAC calculation.

Excel reports receive separate **FRF Diagnostics** and **Quality Control** sheets. PDF reports receive FRF, verified-MAC, and quality-control pages.
