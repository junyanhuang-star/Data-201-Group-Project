# AI use log (Keerat)

Tool: Claude (Anthropic), used as a tutor and coding assistant.

| Date | What I asked for | What the AI produced | What I did / verified |
|---|---|---|---|
| 2026-09-28 | Explain the project requirements and where the group stands | Summary of the directions PDF, the GitHub branches and the next steps | Read the PDF and branches myself |
| 2026-09-28 | Help understanding the dataset | `01_explore_data.ipynb`: data profiling, missing values, messy categories, functional-dependency checks | Ran every cell on my own CSV and read the "What to notice" notes |
| 2026-09-29 | Walk through normalization 1NF → 2NF → 3NF | `02_normalization.ipynb` (12-table schema, cleaning functions, PK/FK/lossless checks) and `keerat_erd.png` | Ran the notebook and checked the integrity outputs |
| 2026-09-29 | Compare my schema with Jun's and Andrei's | `schema_comparison.md` | Checked the claims against the branches before the meeting |
| 2026-09-30 | Asked whether the 2NF example used real data | It didn't: the AI had invented a `category` column. The 2NF section was rewritten to use only real columns, and `category` was removed from the schema and ERD. | Re-ran notebook 02 |

All results were run on the real data. The design reasoning in these files is what I will explain in the presentation.
