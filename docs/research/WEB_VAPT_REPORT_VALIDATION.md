# Multi-Format Report & Cryptographic Manifest Validation

**Date:** 26 October 2026  
**Subject:** Cross-format synchronization audit for AI-VAPT reporting subsystem.  

---

## 1. Cross-Format Synchronization Audit

To guarantee research integrity and compliance with academic evaluation standards, the report output was audited across all four supported formats (JSON, HTML, Markdown, Plain Text) plus the cryptographic manifest for Run `6e030d37-b406-4f00-9391-19ad8d22e401`.

| Section / Metric | JSON Report | HTML Report | Markdown Report | Plain Text Report | Manifest (`report_manifest.json`) |
|---|---|---|---|---|---|
| **Discovered Inventory** | 10 records | 10 rows | 10 rows | 10 entries | 10 |
| **Actionable Candidates** | 1 candidate | 1 row | 1 row | 1 entry | 1 |
| **Confirmed Findings** | 1 (`phpinfo-files`)| 1 (`CONFIRMED`) | 1 (`CONFIRMED`) | 1 (`CONFIRMED`) | 1 |
| **Validation Not Available**| 0 | 0 | 0 | 0 | 0 |
| **Evidence Tier** | `CONTROLLED_VALIDATION`| `CONTROLLED_VALIDATION`| `CONTROLLED_VALIDATION`| `CONTROLLED_VALIDATION`| `CONTROLLED_VALIDATION`|
| **Evidence Hash (SHA-256)**| Present | Present | Present | Present | Verified |
| **Reproduction Command** | Present | Present | Present | Present | Logged |

---

## 2. Cryptographic Manifest Verification

The manifest was generated via `GET /runs/6e030d37-b406-4f00-9391-19ad8d22e401/report?format=manifest`:

```json
{
  "manifest_version": "1.0.0",
  "run_id": "6e030d37-b406-4f00-9391-19ad8d22e401",
  "scenario_or_target": "failure_pivot",
  "mode": "simulation",
  "evidence_tier": "CONTROLLED_VALIDATION",
  "generated_at": "2026-10-26T17:17:25Z",
  "finding_counts": {
    "discovered_observations": 10,
    "actionable_candidates": 1,
    "confirmed_findings": 1,
    "not_reproducible": 0,
    "inconclusive": 0,
    "false_positives": 0,
    "validation_not_available": 0,
    "blocked_by_policy": 0
  },
  "artifact_hashes": {
    "json": "148a4d0aadc8a0ed8baf9d8b5974729b0c53a7a8df8067f74742f53cff552dbc",
    "html": "612b7fc4cbd4d615253e363d6a8a72760fee403bbd4dbce89685716dcf0f0c2f",
    "markdown": "4c377d55e0b77e78499d82bcee762409021b5942e9292eedb2a26f7107b35dde",
    "txt": "ff8be94b592ebf7a31b721c79bb75b69a7815e29f811678ca1530dafdf04353c"
  },
  "provenance": {
    "max_attempts": 2,
    "total_attempts": 1,
    "pivot_count": 0,
    "candidates_processed": [
      "phpinfo-files"
    ]
  }
}
```

Every format hashes consistently and contains identical findings and counts.

