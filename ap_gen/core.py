"""Shared helpers used by the ERP and workflow data generators."""

import calendar, json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
import xlsxwriter


def load_config(path="config/config.yaml"):
    """Load a YAML configuration file and return it as a dictionary."""
    with open(path, encoding="utf-8") as f:
        return


def month_end(year, month):
    """Return the last day of a calendar month as a pandas timestamp."""
    return pd.Timestamp(year, month, calendar.monthrange(year, month)[1])


def directories(cfg):
    """Create and return the output directories used by the pipeline."""
    root = Path(cfg["project"]["output"])
    result = {
        "erp": root / "erp",
        "workflow": root / "workflow",
        "manifest": root / "manifest",
        "validation": root / "validation",
        "staging": root / "staging",
    }
    for path in result.values():
        path.mkdir(parents=True, exist_ok=True)
    return result


def output_formats(cfg):
    """Return requested output formats after checking their configuration."""
    formats = [
        str(value).lower() for value in cfg["project"].get("output_formats", ["xlsx"])
    ]
    if not formats or any(value not in {"csv", "xlsx"} for value in formats):
        raise ValueError("project.output_formats must contain csv and/or xlsx")
    return formats


def save_json(value, path):
    """Write JSON data, creating the destination folder when necessary."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, default=str)


def write_csv(df, path):
    """Write a dataframe to CSV without adding a pandas index column."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_xlsx(df, path, sheet):
    """Write a dataframe to a formatted, filterable Excel worksheet."""
    if len(df) > 1_048_575:
        raise ValueError("Excel worksheet limit exceeded")

    wb = xlsxwriter.Workbook(
        str(path),
        {"constants_memory": True, "strings_to_urls": False},
    )
    ws = wb.add_worksheet(sheet)
    header = wb.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
    date_format = wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})

    ws.freeze_panes(1, 0)
    for column, name in enumerate(df.columns):
        ws.write(0, column, name, header)

    if len(df.columns):
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)

    # Write rows one at a time so Xlsxwriter can use constant-memory mode.
    for row_number, row in enumerate(df.itertuples(index=False, name=None), 1):
        for column, value in enumerate(row):
            if value is None or pd.isna(value):
                continue
            if isinstance(value, pd.Timestamp):
                value = value.to_pydatetime()
            if isinstance(value, np.generic):
                value = value.item()
            if isinstance(value, datetime):
                ws.write_datetime(row_number, column, value, date_format)
            else:
                ws.write(row_number, column, value)

    wb.close()


def supplier_master(cfg):
    """Build the repeatable synthetic supplier master from configuration values."""
    md = cfg["master"]
    n = md["supplier_count"]

    return pd.DataFrame(
        {
            "SUPPLIER_ID": [f"SUP-{i:06d}" for i in range(1, n + 1)],
            "SUPPLIER_NAME": [f"Synthetic Supplier {i:06d}" for i in range(1, n + 1)],
            "COUNTRY_CODE": [
                md["countries"][i % len(md["countries"])] for i in range(n)
            ],
            "CURRENCY": [md["currencies"][i % len(md["currencies"])] for i in range(n)],
            "CRITICAL_FLAG": ["Y" if i % 20 == 0 else "N" for i in range(n)],
        }
    )


def sample_indices(rng, length, rate):
    """Choose unique row positions for an anomaly rate between zero and one."""
    count = int(length * rate)
    return [] if count == 0 else rng.choice(length, count, replace=False)


def erp_anomalies(df, rng, rates):
    """Apply configured data-quality scenarios to generated ERP rows."""
    if not rates["enabled"]:
        return df

    ix = sample_indices(rng, len(df), rates["missing_supplier"])
    df.loc[ix, "SUPPLIER_NAME"] = None
    df.loc[ix, "DQ_SCENARIO"] = "MISSING_SUPPLIER"

    ix = sample_indices(rng, len(df), rates["malformed_date"])
    df.loc[ix, "DUE_DATE_RAW"] = "2206-13-40"
    df.loc[ix, "DQ_SCENARIO"] = "MALFORED_DATE"

    ix = sample_indices(rng, len(df), rates["late_arrival"])
    df.loc[ix, "LAST_UPDATED_TIMESTAMP"] += pd.Timedelta(days=45)
    df.loc[ix, "LATE_ARRIVAL_FLAG"] = 1
    df.loc[ix, "DQ_SCENARIO"] = "LATE_ARRIVAL"

    ix = sample_indices(rng, len(df), rates["status_conflict"])
    df.loc[ix, "PAYMENT_STATUS"] = "PAID"
    df.loc[ix, "PAYMENT_DATE"] = pd.NaT
    df.loc[ix, "DQ_SCENARIO"] = "STATUS_CONFLICT"

    ix = sample_indices(rng, len(df), rates["inconsistent_case"])
    df.loc[ix, "PAYMENT_STATUS"] = "paid "
    df.loc[ix, "DQ_SCENARIO"] = "INCONSISTENT_CASE"

    target = sample_indices(rng, len(df), rates["duplicate_erp"])
    if len(target):
        source = rng.choice(len(df), len(target), replace=False)
        df.iloc[target] = df.iloc[source].to_numpy()
        df.loc[target, "DQ_SCENARIO"] = "DUPLICATE_ERP_ROW"

    return df


def workflow_anomalies(df, rng, rates):
    """Apply configured orphan and duplicate scenario to workflow events."""
    if df.empty or not rates["enabled"]:
        return df

    ix = sample_indices(rng, len(df), rates["orphan_workflow"])
    df.loc[ix, "INVOICE_ID"] = "INV-ORPHAN"
    df.loc[ix, "DQ_SCENARIO"] = "ORPHAN_REFERENCE"

    count = int(len(df) * rates["duplicate_workflow"])
    if count:
        duplicate = df.iloc[rng.choice(len(df), count, replace=False)].copy()
        duplicate["DQ_SCENARIO"] = "DUPLICATE_WORKFLOW"
        df = pd.concat([df, duplicate], ignore_index=True)

    return df
