"""Check generated ERP and workflow files for expected structure and links."""

import argparse, json
import pandas as pd
from ap_gen.core import directories, load_config, output_formats, save_json


def validate(cfg):
    """Run file-count, row-count, foreign-key, and chronology checks."""
    dirs = directories(cfg)
    formats = output_formats(cfg)
    extension = "xlsx" if "xlsx" in formats else "csv"
    year = cfg["project"]["year"]
    erp_files = sorted(dirs["erp"].glob(f"ERP *{year}.{extension}"))
    workflow_files = sorted(dirs["workflow"].glob(f"Invoices *{year}.{extension}"))
    checks, valid_ids = [], set()

    checks.append(
        {
            "check": "ERP file count",
            "passed": len(erp_files) == cfg["project"]["months"],
        }
    )
    checks.append(
        {
            "check": "Workflow file count",
            "passed": len(workflow_files) == cfg["project"]["months"],
        }
    )

    # Header rows identify the invoice IDs that workflow events are allowed to reference.
    for file in erp_files:
        if extension == "xlsx":
            df = pd.read_excel(
                file, usecols=["INVOICE_ID", "LINE_NUMBER", "DQ_SCENARIO"]
            )
        else:
            df = pd.read_csv(file, usecols=["INVOICE_ID", "LINE_NUMBER", "DQ_SCENARIO"])
        valid_ids.update(df.loc[df.LINE_NUMBER == 1, "INVOICE_ID"].astype(str))
        checks.append(
            {
                "check": f"{file.name} rows",
                "passed": len(df) == cfg["project"]["rows_per_month"],
                "actual": len(df),
            }
        )

    orphan_errors = chronology_errors = 0
    for file in workflow_files:
        df = pd.read_excel(file) if extension == "xlsx" else pd.read_csv(file)
        if df.empty:
            continue
        normal = df[df.DQ_SCENARIO != "ORPHAN_REFERENCE"].copy()
        orphan_errors += int((~normal.INVOICE_ID.astype(str).isin(valid_ids)).sum())
        ordered = normal.sort_values(["WORKFLOW_ID", "EVENT_SEQUENCE"])
        timestamps = pd.to_datetime(ordered.EVENT_TIMESTAMP, errors="coerce")
        chronology_errors += int(
            (
                timestamps.groupby(ordered.WORKFLOW_ID).diff().dt.total_seconds() < 0
            ).sum()
        )

    checks.extend(
        [
            {
                "check": "Normal workflow foreign keys",
                "passed": orphan_errors == 0,
                "errors": orphan_errors,
            },
            {
                "check": "Workflow chronology",
                "passed": chronology_errors == 0,
                "errors": chronology_errors,
            },
        ]
    )

    report = {
        "status": "PASS" if all(x["passed"] for x in checks) else "FAIL",
        "checks": checks,
    }
    save_json(report, dirs["validation"] / "validation_report.json")
    return report


if __name__ == "__main__":
    # Print the report directly when validation is requested from the command line.
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    print(json.dumps(validate(load_config(parser.parse_args().config)), indent=2))
