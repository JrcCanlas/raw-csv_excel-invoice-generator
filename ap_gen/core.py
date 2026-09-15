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
