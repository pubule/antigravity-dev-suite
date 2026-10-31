# 🌐 Web Protocols & Authentication Audit Guide

Use this reference when auditing HTTP services, web APIs, authentication flows, and network communications.

---

## 1. Authentication & Session Integrity
- **JWT & Token Validation**:
  - Verify signature algorithm enforcement (reject `alg: none` and asymmetric/symmetric key confusion).
  - Verify expiration (`exp`), audience (`aud`), and issuer (`iss`) checks.
  - Check for sensitive claims stored unencrypted in JWT payload.
- **Session Lifecycle**:
  - Verify session tokens rotate after privilege transitions (login, role change).
  - Check for session fixation vulnerabilities.
  - Verify secure cookie attributes: `HttpOnly`, `Secure`, `SameSite=Strict` or `Lax`.

---

## 2. Authorization & Access Control
- **Broken Object Level Authorization (BOLA / IDOR)**:
  - Check every database query for explicit tenant, organization, or user ownership scoping.
  - Do not trust client-supplied IDs without verifying session authorization.
- **Broken Function Level Authorization (BFLA)**:
  - Verify admin or elevated endpoints enforce role checks at the route and controller level.
  - Inspect HTTP method switches (e.g., `POST` protected, but `GET` or `PUT` unrestricted).

---

## 3. Server-Side Request Forgery (SSRF)
- **Outbound HTTP Calls**:
  - Validate and whitelist hostnames before initiating outbound HTTP requests.
  - Prohibit connections to loopback (`127.0.0.1`, `::1`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and link-local addresses (`169.254.169.254`).
  - Guard against DNS rebinding attacks by validating resolved IP addresses prior to connection.

---

## 4. HTTP Framing & Caching
- **Request Smuggling**:
  - Check front-end proxy to backend server header consistency (`Transfer-Encoding` vs `Content-Length`).
- **Web Cache Deception / Poisoning**:
  - Inspect unkeyed request headers influencing cached responses.
  - Check path extension confusion on cached static versus dynamic endpoints.
