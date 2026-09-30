# Notebooks

Colab drivers the text-analytics workstream used on 25–27 Sep 2026 to run
the repository's own modules on a GPU. They hold no project logic of their
own: each cell calls a module that is in the repository, so the RUNBOOK
commands reproduce everything here. They are kept as the record of how the
taxonomy, the labelling sheets and the first fine-tuned models were made.

**Committed without outputs.** Saved outputs print corpus text, including
staff email addresses from investor-relations PDFs. Clear all outputs before
committing (Jupyter: Edit → Clear All Outputs); `tests/test_notebooks.py`
fails otherwise.

| notebook | what it ran | produced | notes |
|---|---|---|---|
| `AspectDiscovery.ipynb` | `aspects.discover` on the 24 Sep corpus | the 338-cluster run behind the 10-aspect taxonomy ([evidence](../docs/evidence/aspect-taxonomy-2026-09-25.md)) | |
| `AssignmentTOCandidates_(Updated).ipynb` | `aspects.assign` with the 10-aspect config, sentiment on a 12,000-pair sample, `export_candidates`, `export_blind_test` | the candidate and blind test sheets that were labelled | The saved copy shows `aspects.assign` failing on a corrupt embeddings upload; the sheets that were labelled came from a later run that worked. Its runtime CUDA patch is now in the code (`config/device.py`), and the 12,000-pair sample, a Colab-quota workaround, is unnecessary now that scoring classifies each sentence once. Candidates were stratified within that sample, not the whole corpus. |
| `Cohens_K.ipynb` | `train.agreement` on the two annotators' sheets | the agreement figures ([evidence](../docs/evidence/annotation-agreement-2026-09-27.md)) | Its row counts (302, 1,350) were inflated by duplicated pairs; the tool now counts each pair once. |
| `Training.ipynb` | `train.finetune` for seeds 42, 1 and 7, `train.evaluate` for 42 and 1 | the first fine-tuned models | Trained on labels that still had duplicates and five test sentences in train/dev; seed 7 was never evaluated. Results, and the rerun on cleaned labels: [evidence](../docs/evidence/finetune-2026-09-30.md). |

The notebooks unzip copies of the repository and its data inside the Colab
runtime (`plp-project-main.zip`, uploaded `plp.db`); none of those files are
in git. The RUNBOOK's "Running on a Colab GPU" section is the maintained
version of the same workflow.
