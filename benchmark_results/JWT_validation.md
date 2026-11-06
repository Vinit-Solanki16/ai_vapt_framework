# Phase 14.1 — JWT Claim Inspection & Sensitive Data Exposure Validation

**Correlated Ground Truth Finding:** Hermes F-02 (*Sensitive Data Exposure: Password Hash in JWT*)  
**OWASP Category:** A02:2021 – Cryptographic Failures / A04:2021 – Insecure Design  
**CWE:** CWE-312 (Cleartext Storage of Sensitive Information) / CWE-916 (Use of Password Hash With Insufficient Computational Effort)  
**Implementation Module:** [`strix/core/scanner/jwt_inspector.py`](file:///home/vinit/STRIX/strix/strix/core/scanner/jwt_inspector.py)  
**Live Run Evidence:** [`run-7be22192`](file:///home/vinit/STRIX/strix/benchmark_results/runs/run-7be22192.json)  

---

## 1. Vulnerability Background

In modern single-page applications using JSON Web Tokens (JWT) for stateless session management, tokens are issued by the authentication service and stored on the client (e.g., in `localStorage` or session cookies). 

A critical vulnerability occurs when the backend application serializes sensitive user database attributes directly into the JWT payload. In OWASP Juice Shop, authenticating as `demo` returns a JWT whose payload contains the entire user record, including the user's unsalted MD5 password hash.

Because JWT payloads are simply Base64URL-encoded (RFC 7519) and not encrypted, any entity in possession of the token (including malicious scripts via XSS or browser history) can read the user's password hash in plaintext and crack it offline.

---

## 2. Technical Validation Methodology

[`JWTInspector`](file:///home/vinit/STRIX/strix/strix/core/scanner/jwt_inspector.py) performs non-destructive, safe inspection of issued JWTs.

### 2.1 RFC 7519 Payload Decoding (Signature Unverified)
To assess whether sensitive data is exposed, the inspector splits the token into `header.payload.signature` components and parses the payload dictionary without attempting to verify or forge the signature:

> [!NOTE]
> Per RFC 7519 Section 7.2, decoding the payload claims is a client-side parsing operation. The inspector explicitly attaches the following integrity disclaimer:
> `Decoded JWT Payload (RFC 7519, signature unverified)`

### 2.2 Sensitive Claim Discovery & Unsalted MD5 Detection
The inspector recursively searches the claims dictionary for sensitive keys:
- `password`
- `totpSecret`
- `hash`
- `salt`
- `secret`
- `private_key`

When a sensitive claim is located, its format is analyzed:
- A 32-character hexadecimal string matching `^[a-fA-F0-9]{32}$` confirms an **unsalted MD5 or NTLM hash**, an obsolete and broken cryptographic primitive.
- The inspector classifies the finding with **HIGH severity** and CVSS score **7.5**.

### 2.3 Safe Evidence Redaction
To prevent Strix from itself becoming a conduit for leaked credentials, the exposed hash is masked before inclusion in SARIF reports and decision logs:
- **Raw Leaked Hash:** `fe01ce2a7fbac8fafaed7c982a04e229` (the MD5 hash of `demo`)
- **Redacted Evidence Snippet:** `fe01...[REDACTED]...e229`

---

## 3. Live Assessment Verification & Evidence

In live run [`run-7be22192`](file:///home/vinit/STRIX/strix/benchmark_results/runs/run-7be22192.json), Strix authenticated against `http://127.0.0.1:3000/rest/user/login` and analyzed the returned session token.

### 3.1 Live Finding Extract
- **Finding ID:** `find-jwt-password-leak`
- **Title:** `Sensitive Data Exposure: Password Hash in JWT`
- **Severity:** `HIGH`
- **CVSS Score:** `7.5`
- **OWASP:** `A05:2021 - Security Misconfiguration` (OWASP Top 10)
- **CWE:** `CWE-312`
- **Evidence SHA-256 Hash:** `a1e88a36527be6ea7ee391c17a4ae696e863054575964d2c36a64d62a5027fb0`

### 3.2 Evidence Snippet
```http
Decoded JWT Payload (RFC 7519, signature unverified):
Claim: data.password = fe01...[REDACTED]...e229 (Unsalted MD5 password hash)
Claims Summary: {"status": "success", "data": {"id": 6, "username": "", "email": "demo", "password": "fe01...[REDACTED]...e229", "role": "customer", "deluxeToken": "", "lastLoginIp": "127.0.0.1", "profileImage": "/assets/public/images/uploads/default.svg"}}
```

### 3.3 Remediation Recommendation
1. Exclude the `password`, `totpSecret`, and any cryptographic material from the JWT payload during token serialization.
2. If user attributes are required by the frontend, transmit only non-sensitive identity metadata (e.g., `id`, `email`, `role`).
3. Migrate password storage from obsolete unsalted MD5 to Argon2id, bcrypt (work factor >= 12), or PBKDF2 with unique cryptographic salts.

