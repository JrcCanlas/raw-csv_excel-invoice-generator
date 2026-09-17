"""Generate synthetic accounts-payable ERP distribution records."""

import argparse
import numpy as np
import pandas as pd

from ap_gen.core import (
    directories,
    erp_anomalies,
    load_config,
    month_end,
    output_formats,
    save_json,
    supplier_master,
    write_csv,
    write_xlsx,
)

FX = {
    "USD": 1,
    "PHP": 0.017,
    "SGD": 0.74,
    "AUD": 0.66,
    "JPY": 0.0068,
    "CAD": 0.74,
    "GBP": 1.28,
    "EUR": 1.09,
}


def build_month(cfg, month, rng, suppliers):
    """Create one month of ERP rows from suppliers and configure probabilities."""
    p, md, ec = cfg["project"], cfg["master"], cfg["erp"]
    (
        rows,
        year,
    ) = (
        p["rows_per_month"],
        p["year"],
    )
    start, end = pd.Timestamp(year, month, 1), month_end(year, month)

    # First choose invoice line counts, then trim the final invoice to the exact row total.
    counts = []
    while sum(counts) < rows:
        counts.extend(
            rng.choice(ec["line_counts"], max(1000, rows // 3), p=ec["line_weights"])
        )
    counts = np.asarray(counts)
    invoice_count = np.searchsorted(np.cumsum(counts), rows) + 1
    invoice_index = np.repeat(np.arange(invoice_count), counts[:invoice_count])[:rows]
    line_number = (
        pd.Series(invoice_index).groupby(invoice_index).cumcount().to_numpy() + 1
    )

    invoice_ids = np.array(
        [f"INV-{year}{month:02d}-{i:07d}" for i in range(invoice_count)]
    )

    created = start + pd.to_timedelta(
        ((end - start).days * rng.beta(3.5, 1.8, invoice_count)).astype(int), unit="D"
    )
    received = created - pd.to_timedelta(rng.integers(0, 4, invoice_count), unit="D")
    invoice_date = received - pd.to_timedelta(
        rng.integers(0, 11, invoice_count), unit="D"
    )
    posting = created + pd.to_timedelta(rng.integers(0, 9, invoice_count), unit="D")

    supplier_index = np.minimum(rng.zipf(1.35, invoice_count), len(suppliers)) - 1
    supplier = suppliers.iloc[supplier_index].reset_index(drop=True)

    terms = rng.choice(md["payment_terms"], invoice_count, p=md["payment_term_weights"])
    due = invoice_date + pd.to_timedelta(terms, unit="D")
    currency = supplier["CURRENCY"].to_numpy()
    fx = np.array([FX[x] for x in currency])

    po_flag = rng.random(invoice_count) < ec["po_rate"]
    po_number = np.where(
        po_flag,
        [f"PO-{year}-{x:08d}" for x in rng.integers(1, 99_999_999, invoice_count)],
        None,
    )

    quantity = rng.integers(1, 21, rows)
    unit_price = rng.lognormal(4.2, 1.0, rows)
    line_amount = np.round(quantity * unit_price, 2)
    credit = rng.random(invoice_count) < ec["credit_memo_rate"]
    line_amount *= np.where(credit[invoice_index], -1, 1)
    invoice_total = np.bincount(invoice_index, line_amount, minlength=invoice_count)

    status = rng.choice(ec["statuses"], invoice_count, p=ec["status_weights"])
    payment_date = pd.Series(
        due + pd.to_timedelta(np.rint(rng.normal(-2, 10, invoice_count)), unit="D")
    ).where(status == "PAID")
    paid = np.where(
        status == "PAID",
        invoice_total,
        np.where(
            status == "PARTIALLY_PAID",
            invoice_total * rng.uniform(0.1, 0.9, invoice_count),
            0,
        ),
    )

    df = pd.DataFrame(
        {
            "ERP_RECORD_ID": [f"ERP-{year}{month:02d}-{i:07d}" for i in range(rows)],
            "DOCUMENT_ID": [f"DOC-{x}" for x in invoice_ids[invoice_index]],
            "INVOICE_ID": invoice_ids[invoice_index],
            "INVOICE_NUMBER": invoice_ids[invoice_index],
            "LINE_NUMBER": line_number,
            "DISTRIBUTION_NUMBER": line_number,
            "INVOICE_HEADER_FLAG": (line_number == 1).astype(int),
            "SUPPLIER_ID": supplier["SUPPLIER_ID"].to_numpy()[invoice_index],
            "SUPPLIER_NAME": supplier["SUPPLIER_NAME"].to_numpy()[invoice_index],
            "CRITICAL_SUPPLIER_FLAG": supplier["CRITICAL_FLAG"].to_numpy()[
                invoice_index
            ],
            "REGION": rng.choice(md["regions"], rows),
            "COUNTRY_CODE": supplier["COUNTRY_CODE"].to_numpy()[invoice_index],
            "COMPANY_CODE": rng.choice(md["companies"], rows),
            "BUSINESS_UNIT": rng.choice(md["business_units"], rows),
            "COST_CENTER": [f"CC-{x:05d}" for x in rng.integers(1, 5000, rows)],
            "GL_ACCOUNT": [f"6{x:05d}" for x in rng.integers(10000, 99999, rows)],
            "CATEGORY": rng.choice(md["categories"], rows),
            "QUANTITY": quantity,
            "UNIT_PRICE": np.round(unit_price, 2),
            "LINE_AMOUNT_DOC": line_amount,
            "LINE_AMOUNT_USD": np.round(line_amount * fx[invoice_index], 2),
            "INVOICE_AMOUNT_DOC": np.round(invoice_total[invoice_index], 2),
            "INVOICE_AMOUNT_USD": np.round(
                invoice_total[invoice_index] * fx[invoice_index], 2
            ),
            "CURRENCY": currency[invoice_index],
            "FX_RATE": fx[invoice_index],
            "PAYMENT_TERM_DAYS": terms[invoice_index],
            "PO_NUMBER": po_number[invoice_index],
            "PO_NON_PO": np.where(po_flag[invoice_index], "PO", "NON_PO"),
            "MATCH_TYPE": np.where(po_flag[invoice_index], "3_WAY", "NONE"),
            "INVOICE_TYPE": np.where(credit[invoice_index], "CREDIT_MEMO", "STANDARD"),
            "INVOICE_DATE": invoice_date[invoice_index],
            "RECEIPT_DATE": received[invoice_index],
            "CREATION_DATE": created[invoice_index],
            "POSTING_DATE": posting[invoice_index],
            "DUE_DATE_RAW": pd.Series(due[invoice_index]).dt.strftime("%Y-%m-%d"),
            "PAYMENT_DATE": payment_date.iloc[invoice_index].to_numpy(),
            "PAYMENT_STATUS": status[invoice_index],
            "AMOUNT_PAID": np.round(paid[invoice_index], 2),
            "AMOUNT_REMAINING": np.round(
                invoice_total[invoice_index] - paid[invoice_index], 2
            ),
            "SOURCE_SYSTEM": rng.choice(
                ["ERP_CORE", "ERP_LEGACY", "MANUAL_UPLOAD"], rows
            ),
            "LAST_UPDATED_TIMESTAMP": created[invoice_index]
            + pd.to_timedelta(rng.integers(0, 31, rows), unit="D"),
            "LATE_ARRIVAL_FLAG": 0,
            "DQ_SCENARIO": "NORMAL",
        }
    )
    return erp_anomalies(df, rng, cfg["anomalies"])


def generate(cfg, progress=None):
    """Generate the configured ERP files and write their manifest."""
    dirs = directories(cfg)
    formats = output_formats(cfg)
    progress = progress or print
    suppliers = supplier_master(cfg)
    seeds = np.random.SeedSequence(cfg["project"]["seed"]).spawn(
        cfg["project"]["months"]
    )
    manifest = []

    for month in range(1, cfg["project"]["months"] + 1):
        df = build_month(cfg, month, np.random.default_rng(seeds[month - 1]), suppliers)
        end = month_end(cfg["project"]["year"], month)
        path = dirs["erp"] / f"ERP {end:%m%d%Y}.xlsx"
        if "xlsx" in formats:
            write_xlsx(df, path, "ERP_RAW")
        if "csv" in formats:
            write_csv(df, dirs["erp"] / f"ERP {end:%m%d%Y}.csv")
        manifest.append(
            {
                "file": path.name if "xlsx" in formats else f"ERP {end:%m%d%Y}.csv",
                "rows": len(df),
            }
        )
        progress(f"ERP {end:%m%d%Y}: SUCCESS ({len(df):,} rows)")

    save_json(manifest, dirs["manifest"] / "erp_manifest.json")


if __name__ == "__main__":
    # Keep this module usable both as an importable library and as a CLI script.
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    generate(load_config(parser.parse_args().config))
