# Softlock prevalence and prevention costs

Minimal reproduction package for the Sturgeon empirical study.
It contains code, measured records, movement-model validation, learned schemes,
configuration inputs, and the original calibration decisions needed by the analysis.
It contains no manuscript, cover letter, author details, audit manifests, file
digests, draft reports, plot exports, or duplicate result tables.

## Recompute the published results

Use Python 3.9 (the measured environment used 3.9.13). From this directory:

```sh
python -m pip install -r requirements.txt
python verify_data.py
python reproduce.py
```

`verify_data.py` checks all 5,550 measured outputs against the movement model.
`reproduce.py` runs ten analysis stages in a temporary copy and writes XLS
summaries to `results/`. No generation is needed. The supplied records are not
overwritten. Main Table I is in `results/replication/results.xls`; prospective
ratios and projected calibration costs are in `results/prospective/results.xls`.
Density estimates are in `results/density_results.xls` and
`results/training_comparison.xls`. Other outputs cover paired execution,
boundary semantics, timing decomposition and decision sensitivity.

Each `attempts.xls` contains measured times, seeds, conditions, acceptance
metrics and `level_content`. Pairing and uniqueness use actual level text.
`diagnostic_inputs.xls` compactly stores the earlier level filenames and the
timing lines needed by the original structural and timing diagnostics; the
analysis wrapper restores these only inside its temporary directory.
Environment files retain startup times used in calibration cost accounting.
Calibration decisions and acquisition costs must remain inputs: regenerating
them would replace the originally measured information available before holdout.

## Run fresh generation experiments

New wall-clock measurements will vary. Reanalysis of saved measurements and
fresh timing experiments are different operations. The original machine was an
AMD Ryzen 9 7950X, Windows, Python 3.9.13. Drivers refuse existing run folders.

Create an empty experiment copy in a location of your choice:

```sh
python new_experiment.py ../fresh-experiment
```

Clone https://github.com/crowdgames/sturgeon-pub alongside that new folder and
check out version `25bf8eef7006de04a3fcdd9e9cab18cb8b472129`.
This source-version identifier is retained because it selects the implementation;
it is not an artifact-integrity manifest. Install the pinned requirements and
run the following inside `fresh-experiment`:

```sh
python setup_experiment.py
python prepare_training_b.py
python prepare_extension.py
python refine_external.py
python check_validator.py
python run_pilot.py --name followup --mechanics driller --count 100 --constrained-count 20 --seed-start 3000 --constrained-seed-offset 100000 --walls 50
python run_density.py
python run_training_b.py
python run_extension.py timing
python run_extension.py calibration
python analyze_extension.py freeze
python run_extension.py evaluation
python analyze_extension.py summarize
python run_replication.py 1
python run_replication.py 2
python run_replication.py 3
python analyze_replication.py
python analyze_prospective.py historical
python run_prospective.py calibration
python analyze_prospective.py calibration
python run_prospective.py session-1
python run_prospective.py session-2
python analyze_prospective.py analyze
```

Earlier exploratory pilot and density-control records remain available for
diagnostics, but are not required to rerun the principal experiments above.
Their exact generation settings are recorded in their environment files.
Source preparation reconstructs the C pattern amendment before any C outputs.
The historical intermediate `nbr-plus` audit is retained in this setup sequence
because its measured preparation cost was included in the original accounting.

## Interpretation and provenance

The 5,550 records include repeated measurements of the same generated draws;
they are not 5,550 independent levels. Confidence intervals are pointwise and
conditional on observed sessions. Synthetic sleeps do not model an independent
game or establish a real deployment threshold. R and G satisfy the same tested
safety property but need not generate the same content distribution.

This is a compact reproduction export. Integrity digests and archival audit
files were intentionally omitted; it is not a standalone proof of the chronology
of the original locally frozen protocols. Original records and audit evidence
remain in the full research archive. No measurement value was changed.
Hash-based level comparisons were replaced by direct content comparisons.
Drivers in this export are adapted for reproduction and are not claimed to be
byte-identical to the originally executed scripts. Their timing overhead can differ.

## Third-party material

Sturgeon is an external dependency; use its pinned source and license.
The adapted Zelda geometry retains attribution to the Video Game Level Corpus:
https://github.com/TheVGLC/TheVGLC. Its license is in `extension/VGLC_LICENSE.md`.
Training example B was authored for this study. Do not put the named submission
cover letter or portal metadata in the anonymous repository.

## Excel data format

All supplied data and configuration files use genuine Excel 97-2003 `.xls`.
Measurement workbooks contain one row per execution, with named columns.
The Cell types sheet preserves distinctions between missing values, zero,
Boolean values and strings; it is required for exact round-trip loading.
Nested settings and analysis results use Path / Type / Value tables.
Numerical measurements are numeric cells; the stored binary floating-point
values are preserved exactly. Cell formatting does not round stored values.

The reproduction command reads XLS inputs and writes XLS results. The existing
analysis modules use temporary JSON intermediates inside an automatically
removed temporary directory. No JSON or JSONL files are distributed.
Fresh generation drivers still use their original internal record format;
run `python export_excel.py` after finishing a fresh experiment to convert
those files to XLS and remove the converted JSON/JSONL files.
