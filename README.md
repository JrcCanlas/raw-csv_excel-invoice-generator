# Synthetic AP Invoice Generator

Generates monthly raw AP ERP distribution files and related workflow-event files.

## Project Flow

![High Level Architecture](images/Synthetic%20AP%20Invoice%20Generator.jpg)

## Project convention

- `config/config.yaml` is the source of truth for the year, month count, row volume, random seed, output location, and anomaly rates.
- The random seed makes generated data repeatable. Change it deliberately when a different dataset is needed.
- ERP files use a distribution-row grain: one row represents one accounting distribution line. Use `INVOICE_HEADER_FLAG=1` when counting or aggregating invoices.
- Workflow files use an event grain: one row represents one lifecycle event for an invoice.
- `DQ_SCENARIO` marks intentionally generated data-quality cases. These are test scenarios, not accidental production errors.
- `run_all.py` is the normal entry point because it generates both datasets and then validates them.
- Generated files belong under `output/`; manifests record generated file names and row counts, while `validation/validation_report.json` records check results.
- Keep generated outputs out of source control when possible. The generator can recreate them from the configuration and seed.
- Run commands from the project root so relative paths such as `config/config.yaml` and `output/` resolve correctly.

## Setup

Use a project-local virtual environment so packages do not conflict with a global or Anaconda installation.

python -m venv .venv

Windows:
.venv\Scripts\activate

macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

The supported interpreter is Python 3.10 or newer. If pandas or NumPy reports a compiled-DLL import error, recreate the virtual environment and reinstall the requirements instead of mixing package managers.

## Trial run

Set `months: 1` and `rows_per_month: 1000` in config/config.yaml.

pytest -q
python run_all.py

The test suite uses small temporary output folders, so it does not overwrite the main generated dataset.

## Full run

Restore `months: 12` and `rows_per_month: 100000`.

python run_all.py --config config/config.yaml

## Individual execution

python erp.py
python workflow.py
python validate.py

## Output

output/erp/ERP 01312026.xlsx
output/erp/ERP 01312026.csv
output/workflow/Invoices 01312026.xlsx
output/workflow/Invoices 01312026.csv
output/manifests/
output/validation/validation_report.json

Set `project.output_formats` to `["xlsx"]`, `["csv"]`, or `["xlsx", "csv"]` to choose the generated file formats.

ERP grain: one accounting distribution row.
Workflow grain: one lifecycle event.

Use INVOICE_HEADER_FLAG=1 when aggregating invoice totals.
Use LINE_AMOUNT_USD when aggregating distributions.

DQ_SCENARIO identifies deliberate test anomalies.

Synthetic test data only. Do not use as real financial records.
