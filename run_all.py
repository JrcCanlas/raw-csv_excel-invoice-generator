"""Run ERP generation, workflow generation, and validation in sequence."""

import argparse
from apgen.core import load_config
from erp import generate as generate_erp
from workflow import generate as generate_workflow
from validate import validate


def run_stage(name, action):
    """Run one pipeline stage and print a consistent status message."""
    print(f"[{name}] RUNNING")
    try:
        result = action()
    except Exception as error:
        print(f"[{name}] FAILED: {error}")
        raise
    print(f"[{name}] SUCCESS")
    return result


def run_validation(config):
    """Validate generated files and raise an error when any check fails."""
    report = validate(config)
    if report["status"] != "PASS":
        raise RuntimeError("validation checks did not pass")
    return report


def main():
    """Parse command-line options and run the complete pipeline."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    run_stage("ERP", lambda: generate_erp(config))
    run_stage("WORKFLOW", lambda: generate_workflow(config))
    run_stage("VALIDATION", lambda: run_validation(config))
    print("Generation and validation completed successfully.")


if __name__ == "__main__":
    main()
