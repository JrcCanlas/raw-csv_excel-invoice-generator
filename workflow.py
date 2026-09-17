"""Generate workflow lifecycle events from ERP invoice headers."""

import argparse, shutil
import numpy as np
import pandas as pd

from ap_gen.core import (
    directories,
    load_config,
    month_end,
    output_formats,
    save_json,
    workflow_anomalies,
    write_csv,
    write_xlsx,
)

USECOLS = [
    "ERP_RECORD_ID",
    "DOCUMENT_ID",
    "INVOICE_ID",
    "INVOICE_NUMBER",
    "LINE_NUMBER",
    "SUPPLIER_ID",
    "PO_NUMBER",
    "COMPANY_CODE",
    "INVOICE_AMOUNT_USD",
    "RECEIPT_DATE",
    "POSTING_DATE",
    "PAYMENT_DATE",
]


def events(headers, rng, cfg, source):
    """Create an ordered event history for each invoice header."""
    result = []
    wc = cfg["workflow"]

    for x in headers.itertuples(index=False):
        wid, sequence = f"WF-{x.INVOICE_ID}", 0
        previous_status, previous_time = "NEW", pd.Timestamp(x.RECEIPT_DATE)

        def add(stage, timestamp, status, reason=None):
            """Append one event while carrying forward status and timestamp."""
            nonlocal sequence, previous_status, previous_time
            timestamp = pd.Timestamp(timestamp)
            sequence += 1
            result.append(
                {
                    "WORKFLOW_EVENT_ID": f"{wid}-{sequence:02d}",
                    "WORKFLOW_ID": wid,
                    "EVENT_SEQUENCE": sequence,
                    "ERP_RECORD_ID": x.ERP_RECORD_ID,
                    "DOCUMENT_ID": x.DOCUMENT_ID,
                    "INVOICE_ID": x.INVOICE_ID,
                    "INVOICE_NUMBER": x.INVOICE_NUMBER,
                    "SUPPLIER_ID": x.SUPPLIER_ID,
                    "PO_NUMBER": x.PO_NUMBER,
                    "COMPANY_CODE": x.COMPANY_CODE,
                    "INVOICE_AMOUNT_USD": x.INVOICE_AMOUNT_USD,
                    "WORKFLOW_STAGE": stage,
                    "PREVIOUS_STATUS": previous_status,
                    "CURRENT_STATUS": status,
                    "PREVIOUS_EVENT_TIMESTAMP": previous_time,
                    "EVENT_TIMESTAMP": timestamp,
                    "STAGE_DURATION_HOURS": round(
                        (timestamp - previous_time).total_seconds() / 3600, 2
                    ),
                    "PROCESSOR_ID": f"USR-{rng.integers(1, wc['processor_count'] + 1):04d}",
                    "EXCEPTION_REASON": reason,
                    "SOURCE_ERP_FILE": source,
                    "DQ_SCENARIO": "NORMAL",
                }
            )
            previous_status, previous_time = status, timestamp

        received = pd.Timestamp(x.RECEIPT_DATE)
        add("RECEIVED", received, "RECEIVED")
        add(
            "VALIDATED",
            received + pd.Timedelta(hours=int(rng.integers(1, 49))),
            "VALIDATED",
        )

        outcome = rng.choice(wc["outcomes"], p=wc["outcome_weights"])
        submitted = previous_time + pd.Timedelta(hours=int(rng.integers(1, 25)))

        if outcome in ("BLOCKED", "PARKED"):
            add(
                outcome,
                submitted,
                outcome,
                rng.choice(
                    ["PO_MISMATCH", "MISSING_RECEIPT", "TAX_VARIANCE", "SUPPLIER_QUERY"]
                ),
            )
            add(
                "RESOLVED",
                previous_time + pd.Timedelta(hours=int(rng.integers(12, 241))),
                "RESOLVED",
            )
            if rng.random() < wc["reopen_rate"]:
                add("REOPENED", previous_time + pd.Timedelta(hours=4), "REOPENED")
            submitted = previous_time + pd.Timedelta(hours=8)

        add("APPROVAL_SUBMITTED", submitted, "IN_APPROVAL")
        decision = previous_time + pd.Timedelta(hours=int(rng.integers(2, 169)))

        if outcome == "REJECTED":
            add("REJECTED", decision, "REJECTED", "INVALID_OR_DUPLICATE_INVOICE")
            continue

        add("APPROVED", decision, "APPROVED")
        posted = max(
            previous_time + pd.Timedelta(hours=1), pd.Timestamp(x.POSTING_DATE)
        )
        add("POSTED", posted, "POSTED")

        if pd.notna(x.PAYMENT_DATE):
            paid = max(posted, pd.Timestamp(x.PAYMENT_DATE))
            add("PAID", paid, "PAID")
            add("RESOLVED", paid + pd.Timedelta(hours=1), "RESOLVED")

    return pd.DataFrame(result)


def generate(cfg, progress=None):
    """Read ERP files, create workflow events, and write monthly outputs."""
    dirs = directories(cfg)
    formats = output_formats(cfg)
    progress = progress or print
    shutil.rmtree(dirs["staging"], ignore_errors=True)
    dirs["staging"].mkdir()
    rng = np.random.default_rng(cfg["project"]["seed"] + 1)
    year = cfg["project"]["year"]

    erp_extension = "xlsx" if "xlsx" in formats else "csv"
    for file in sorted(dirs["erp"].glob(f"ERP *.{erp_extension}")):
        if erp_extension == "xlsx":
            erp = pd.read_excel(file, usecols=USECOLS)
        else:
            erp = pd.read_csv(file, usecols=USECOLS)
        headers = erp[erp.LINE_NUMBER == 1].drop_duplicates("INVOICE_ID")
        df = events(headers, rng, cfg, file.name)
        df["EVENT_TIMESTAMP"] = pd.to_datetime(df["EVENT_TIMESTAMP"])
        df = df[df.EVENT_TIMESTAMP.dt.year == year]

        for month, part in df.groupby(df.EVENT_TIMESTAMP.dt.month):
            csv = dirs["staging"] / f"{month:02d}.csv"
            part.to_csv(csv, mode="a", index=False, header=not csv.exists())

    manifest = []
    for month in range(1, cfg["project"]["months"] + 1):
        csv = dirs["staging"] / f"{month:02d}.csv"
        df = pd.read_csv(csv) if csv.exists() else pd.DataFrame()
        if not df.empty:
            df = workflow_anomalies(df, rng, cfg["anomalies"]).sort_values(
                ["EVENT_TIMESTAMP", "WORKFLOW_ID", "EVENT_SEQUENCE"]
            )

        end = month_end(year, month)
        path = dirs["workflow"] / f"Invoices {end:%m%d%Y}.xlsx"
        if "xlsx" in formats:
            write_xlsx(df, path, "WORKFLOW_RAW")
        if "csv" in formats:
            write_csv(df, dirs["workflow"] / f"Invoices {end:%m%d%Y}.csv")
        manifest.append(
            {
                "file": (
                    path.name if "xlsx" in formats else f"Invoices {end:%m%d%Y}.csv"
                ),
                "rows": len(df),
            }
        )
        progress(f"Workflow {end:%m%d%Y}: SUCCESS ({len(df):,} events)")

    save_json(manifest, dirs["manifest"] / "workflow_manifest.json")
    shutil.rmtree(dirs["staging"], ignore_errors=True)


if __name__ == "__main__":
    # Keep this module usable both as an importable library and as a CLI script.
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    generate(load_config(parser.parse_args().config))
