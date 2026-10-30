# Engagement Profile Security & Persistence Review

## 1. Executive Summary

Saved Engagement Profiles provide persistent, reusable authorization scopes so operators and administrators can execute penetration testing workflows without restarting API servers or modifying container environment variables for each assessment.

Prior implementations introduced two critical governance risks:
1. **Implicit External Authorization Defaults:** A pre-seeded sample profile targeting `pentest-ground.com:4280` was marked active with a fabricated authorization reference (`ROE-2026-PENTEST-GROUND-4280`). This treated an illustrative configuration as legal authorization to test.
2. **Runtime State in Git Tracking:** Engagement profile modifications and state were persisted directly in `data/engagements.json` within the repository workspace, risking repository pollution, accidental commits of environment-specific credentials or scopes, and race conditions between Git pulls and runtime updates.
3. **Unprotected Mutating Endpoints:** Profile management endpoints (`POST`, `PUT`, `DELETE` on `/engagements`) lacked access control, allowing any network caller or untrusted web origin to manipulate authorization scopes.

This hotfix (`fix/engagement-profile-security`) hardens profile security, separates read-only templates from mutable runtime storage outside Git, enforces fail-closed authorization semantics, implements API access control, and attaches immutable engagement audit snapshots to every executed assessment.

---

## 2. Threat Model & Scope Boundaries

### 2.1 Threat Vectors

| Threat ID | Threat Description | Severity | Mitigation in Hotfix |
| :--- | :--- | :--- | :--- |
| **THREAT-01** | **Unauthorized External Scanning via Default Profile:** Operator launches scans against an external domain assuming default profiles represent confirmed legal authority. | **High** | External profiles are strictly **inactive by default**. External targets cannot be authorized without explicit operator review and a genuine, non-placeholder RoE reference. |
| **THREAT-02** | **Credential & Target Leaks via Git Commits:** Engagement files stored in the repository are committed and pushed upstream, exposing private target IP addresses, internal domains, or embedded API keys. | **High** | Runtime profile storage moved outside the Git workspace to `~/.ai_vapt_framework/engagements.json`. Repository only tracks immutable `data/engagement_templates.json`. Secret scanner rejects API keys. |
| **THREAT-03** | **Storage Corruption / Tampering:** Corrupted JSON files or disk write failures cause silent data loss or unintended permissive scope matching. | **Medium** | Atomic temporary-file writes with `os.fsync`. Automatic backup of corrupt files (`.corrupt.<timestamp>`). Corrupted state triggers fail-closed isolation (read-only, local-only scopes). |
| **THREAT-04** | **Cross-Origin / Remote Profile Manipulation:** Untrusted web applications (via CSRF/CORS) or remote network clients alter target allowlists to permit unauthorized scanning. | **High** | Mutating endpoints require `X-Admin-Token` / Bearer token when `VAPT_ADMIN_TOKEN` is configured; non-local callers are rejected when token is unconfigured; untrusted `Origin` headers are blocked. |
| **THREAT-05** | **Audit Provenance Mutation:** Modifying or deleting an engagement profile alters the historical authorization record of past completed runs. | **Medium** | Immutable `engagement_snapshot` captured at assessment start and persisted directly into the run record and report evidence provenance. |

---

## 3. Architecture of the Fix

### 3.1 Separate Storage Locations

```
┌────────────────────────────────────────────────────────┐
│  Repository (Git Tracked, Read-Only Templates)         │
│  data/engagement_templates.json                        │
│    ├── eng-local-lab (active, loopback only)           │
│    └── eng-pentest-ground (INACTIVE, placeholder RoE)  │
└────────────────────────────────────────────────────────┘
                           │ (initial seed or fallback)
                           ▼
┌────────────────────────────────────────────────────────┐
│  Runtime User-Data Storage (Outside Git)              │
│  ~/.ai_vapt_framework/engagements.json                 │
│  (configurable via VAPT_ENGAGEMENTS_FILE)              │
│    ├── Atomic write via tempfile + os.replace + fsync  │
│    ├── Automatic corrupt backup (.corrupt.<timestamp>) │
│    └── Secret scanner validation before save           │
└────────────────────────────────────────────────────────┘
```

- **`data/engagement_templates.json`:** Shipped with the repository as read-only default templates.
- **`~/.ai_vapt_framework/engagements.json`:** Canonical mutable storage location. Falls back to `/tmp/.ai_vapt_framework/engagements.json` if user home is not writable. Overrideable via `VAPT_ENGAGEMENTS_FILE` or `VAPT_ENGAGEMENTS_DIR`.
- **`data/engagements*.json`:** Added to `.gitignore` to prevent any untracked local engagement state from entering Git.

### 3.2 Inactive-by-Default External Profiles

`EngagementProfile.is_active()` enforces strict fail-closed requirements:
- Local loopback profiles (`127.0.0.1`, `localhost`) can be active by default for single-user lab demonstrations.
- Any external profile (containing non-loopback hostnames or IPs) **cannot be active** if its `authorization_reference` is missing, empty, or set to a placeholder (e.g., `PENDING_OPERATOR_AUTHORIZATION_REVIEW`, `TODO`, `TEST`, `SAMPLE`).
- An external profile requires explicit operator activation and entry of a genuine RoE document reference or ticket identifier.

### 3.3 Fail-Closed Corruption Handling & Storage Recovery

When loading `engagements.json`:
1. **Genuinely Missing Storage File (First-Run Initialization):**
   - If the storage file does not exist on disk, clean default profiles are initialized from `data/engagement_templates.json` (or safely migrated from legacy `data/engagements.json` if present outside Git).
   - Storage corruption flag remains `False`, and subsequent persistence mutations succeed normally.
2. **Existing Zero-Byte Storage File (Data-Integrity Edge Case):**
   - An existing zero-byte file is treated strictly as **invalid/corrupted storage**, never silently overwritten with default templates.
   - A timestamped backup is immediately created preserving the 0-byte file: `<storage_path>.corrupt.<YYYYMMDDHHMMSS>`.
   - The in-memory manager enters **Fail-Closed Mode** (`storage_corrupted = True`, `last_storage_error = "Engagements storage file is empty (0 bytes)."`).
   - Only the safe default local lab fallback profile (`eng-local-lab`) is retained in memory; external profiles never become active.
   - Mutations (`create_profile`, `update_profile`, `delete_profile`, `_save`) raise `EngagementStorageError` and refuse to overwrite the invalid storage while in isolation mode.
3. **Malformed JSON, Schema Corruption, or Unparseable Data:**
   - A timestamped backup is immediately created: `<storage_path>.corrupt.<YYYYMMDDHHMMSS>`.
   - The in-memory manager enters **Fail-Closed Mode** (`storage_corrupted = True`).
   - Only the safe default local lab profile (`eng-local-lab`) is retained in memory.
   - All external targets are strictly **unauthorized**.
   - Mutations raise `EngagementStorageError` and refuse to overwrite the corrupted file until an operator inspects or restores it.

### 3.4 Secret Scanning & Credential Rejection

All profile fields (`name`, `description`, `authorized_hosts`, `permitted_paths`, `authorization_reference`) are scanned against credential heuristics before creation or update:
- OpenRouter API keys (`sk-or-v1-...`)
- OpenAI API keys (`sk-...`)
- GitHub Personal Access Tokens (`ghp_...`)
- Token/API Key/Password assignment patterns
- PEM Private Keys (`-----BEGIN RSA PRIVATE KEY-----`)

Profiles containing any detected secret patterns are rejected with `EngagementValidationError`.

### 3.5 API Access Control & Origin Protection

Mutating endpoints (`POST /engagements`, `PUT /engagements/{id}`, `DELETE /engagements/{id}`) are guarded by `_verify_admin_access`:
- **When `VAPT_ADMIN_TOKEN` is configured:**
  - Token is required on all mutating requests via `X-Admin-Token` or `Authorization: Bearer <token>`.
  - Constant-time validation using `hmac.compare_digest`.
  - Missing token: HTTP 401 Unauthorized.
  - Invalid token: HTTP 403 Forbidden.
- **When `VAPT_ADMIN_TOKEN` is unset (Default Local Dev):**
  - Permitted only for local loopback callers (`127.0.0.1`, `::1`, `localhost`, `testclient`).
  - Remote / non-loopback callers are rejected with HTTP 403 Forbidden.
- **Untrusted Web Origins:**
  - Mutating requests with an `Origin` header from untrusted third-party domains are rejected with HTTP 403 Forbidden.
- **Diagnostics:**
  - `GET /engagements/diagnostics` reports storage path, corruption status, and profile counts without exposing credentials.

### 3.6 Immutable Run Audit Snapshots

When an assessment is validated and executed:
- The backend captures a frozen `engagement_snapshot` (including profile ID, name, authorized hosts, allowed ports, permitted paths, RoE reference, scanner policy, and timestamp).
- This snapshot is stored in `pipeline_summary["web"]["authorization"]` of the persisted run.
- Subsequent edits, deactivations, or deletions of the engagement profile in the management console have zero effect on the historical audit trail of past runs.

---

## 4. Legacy Migration Behavior

If legacy `data/engagements.json` exists during initial startup:
1. Profiles are parsed and validated.
2. All local profiles retain their status.
3. **All external profiles are automatically forced to `status: "inactive"`**, appending an operator review requirement to their description.
4. Profiles are written to the persistent runtime path (`~/.ai_vapt_framework/engagements.json`).
5. The legacy file is left untouched as an archival backup.

---

## 5. Verification & Testing

The security model is backed by 30 automated tests in `tests/test_saved_engagements.py`:
- `TestEngagementProfileModel`: Validates loopback active defaults, external fail-closed without RoE reference, placeholder rejection, and expiry enforcement.
- `TestEngagementManagerUnit`: Tests template seeding, atomic persistence, validation rejections, path prefix checks, and port checks.
- `TestEngagementSecurityHardening`: Tests secret rejection, corruption backup creation, fail-closed isolation, rollback on write error, legacy migration safety, and audit snapshot immutability.
- `TestEngagementAPI`: Tests list, diagnostics, CRUD lifecycle, admin token authentication (HTTP 401/403/200), CORS origin filtering, HTTP 500 on storage errors, and target validation transitions.

---

## 6. Operator Responsibilities & Limitations

1. **Pre-Assessment Authorization:** The AI-VAPT platform verifies syntactic and structural authorization conformance. It is the operator's legal responsibility to obtain written Rules of Engagement (RoE) from target owners before activating external profiles.
2. **Admin Token Configuration:** In multi-user or network-accessible deployments, administrators MUST configure `VAPT_ADMIN_TOKEN` in the environment to prevent unauthorized scope modifications.
3. **Backup Retention:** If storage corruption occurs, operators can locate timestamped backups adjacent to the runtime file (`~/.ai_vapt_framework/engagements.json.corrupt.<timestamp>`).
