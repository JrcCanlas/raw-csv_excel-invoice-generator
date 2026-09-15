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
