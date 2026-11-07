#!/usr/bin/env python3
"""Run ground-truth finding reliability evaluation and display the markdown report."""

import os

from vapt_platform.env_loader import load_env


load_env()

# Ensure bounded evaluation inference timeout when running evaluation CLI if unset
if "OLLAMA_TIMEOUT_S" not in os.environ and "OLLAMA_REQUEST_TIMEOUT_S" not in os.environ:
    os.environ["OLLAMA_TIMEOUT_S"] = "12.0"

from vapt_platform.evaluation.reliability_evaluator import main


if __name__ == "__main__":
    main()
