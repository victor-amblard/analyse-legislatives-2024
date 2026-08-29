# Seat projections used in the benchmark

`legislatives-2024-seat-ranges.csv` contains the last pre-election ranges used
in the blog. Each row records its source URL and any aggregation applied to make
the published political blocks comparable.

The `actual` column follows the same five-block convention as the source table
(composition at the opening of the Assembly), not the seven-family convention
used by the model. Keeping both conventions separate prevents a nomenclature
difference from being scored as a forecasting error.

The observed five-block totals come from the results row of the
[2024 legislative election source table](https://fr.wikipedia.org/wiki/%C3%89lections_l%C3%A9gislatives_fran%C3%A7aises_de_2024).
For Ifop and Ipsos, `source_url` points to the institutes' original reports; for
Cluster 17 and Harris Interactive it points to that consolidated table because
the original publication is not stored in this repository.
