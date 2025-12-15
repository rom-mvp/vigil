# AgentShield / Vigil - CTO Overview Document

## 1. Executive Summary

**Vigil** is a specialized security gateway designed to sit between client applications and Large Language Models (LLMs). It acts as a reverse proxy that enforces real-time security policies, validates decisions from a central authority (**AgentShield**), and maintains a tamper-evident audit trail.

The system is currently in a **Production-Ready MVP** state. It demonstrates sophisticated security features (Ed25519 signing, Merkle log chains, TEE-compatible verification) but retains some "startup debt" in its code organization (production code in `legacy/` folder) and frontend implementation (vanilla HTML/JS vs. unlinked React code).

## 2. Architecture & Components

The system follows a **Hub-and-Spoke** security model:

### Core Components
1.  **Vigil Gateway (The Enforcer)**
    *   **Role**: Reverse proxy (Flask-based) that intercepts LLM requests.
    *   **Function**:
        *   **Authentication**: Validates API keys and enforces rate limits (Token Bucket).
        *   **Policy Decision**: Queries **AgentShield** for a signed Allow/Block decision.
        *   **Verification**: Cryptographically verifies AgentShield's response (Ed25519 signature, SHA-256 hash) to prevent tampering or replay attacks.
        *   **Fallback**: If AgentShield is unreachable, falls back to a local `FirewallEngine` (regex) and `PIIEngine`.
    *   **Location**: `/workspace/legacy/local_server.py` (Dockerized).

2.  **AgentShield (The Brain)**
    *   **Role**: Centralized policy decision engine.
    *   **Function**: Evaluates requests against complex policies and returns a signed decision.
    *   **Integration**: Decoupled service, communicated with via REST API.

3.  **Audit System (The Truth)**
    *   **Role**: Immutable logging of all decisions.
    *   **Implementation**: **MerkleLogStore** (`merkle_log_store.py`) creates a hash-chained, append-only log file (`logs_append_only.jsonl`), ensuring historical records cannot be altered without detection.

4.  **Dashboard (The View)**
    *   **Current**: Lightweight Flask app serving `dashboard.html`. Provides log viewing and basic metrics.
    *   **Future**: A React/TypeScript frontend exists in `/workspace/frontend/` but is not currently deployed in the main stack.

## 3. Technology Stack

| Component | Technology | Status |
|-----------|------------|--------|
| **Backend** | Python 3.11, Flask | Production |
| **Gateway Logic** | Python (Requests, Ed25519 libraries) | Production |
| **Frontend** | HTML5, Vanilla JS (Current) / React, TS (Planned) | Transitional |
| **Infrastructure** | Docker Compose, Kubernetes (Manifests ready) | Production-Ready |
| **Security** | Ed25519 (Signing), SHA-256 (Hashing) | Robust |
| **Storage** | Local JSONL (MVP) / Postgres (Supported via env) | MVP |

## 4. Security & Compliance Features

The repository exhibits a "Security First" engineering culture:

*   **Zero Trust Architecture**: The gateway does not trust the decision engine implicitly. It verifies signatures and timestamps for every request.
*   **Fail-Closed Design**: System defaults to `BLOCK` or `503` if verification fails or components are unreachable.
*   **Tamper Evidence**: The Merkle chain implementation allows for cryptographic verification of the audit log's integrity.
*   **Replay Protection**: Uses `request_id`, `tenant_id`, and `timestamp` binding to prevent replay attacks.
*   **Hardening**: Includes tests specifically for TEE (Trusted Execution Environment) vulnerabilities and "CTO Audit" scenarios.

## 5. Current State & Code Quality

### Strengths
*   **High-Value Logic**: The core security logic (signing, hashing, logging) is implemented cleanly and is well-tested.
*   **Deployment Ready**: Dockerfiles and Kubernetes manifests are present and look correct.
*   **Documentation**: extensive documentation (`README.md`, `INTEGRATION_GUIDE.md`) covers setup, architecture, and APIs.

### Weaknesses / Technical Debt
*   **Directory Structure**: The primary production code resides in a `legacy/` directory, while a `vigil/` directory exists (containing a `.venv` and other files) which seems to be a separate or abandoned structure. This is confusing for new contributors.
*   **Frontend Disconnect**: A modern React frontend exists (`frontend/`) but the production Docker setup uses the legacy `dashboard.html`.
*   **In-Memory State**: Rate limiting and user sessions are currently in-memory, limiting horizontal scalability without an external store (e.g., Redis).

## 6. Recommendations (Roadmap)

1.  **Refactor Directory Structure**:
    *   Move `legacy/local_server.py` and engines to a proper `src/vigil` package.
    *   Clean up the `vigil/` directory (remove committed `.venv`).
    *   Update Dockerfiles to reflect the new structure.

2.  **Activate Modern Frontend**:
    *   Complete the integration of the `frontend/` (React) application.
    *   Update `Dockerfile.dashboard` to build and serve the React assets.

3.  **Externalize State**:
    *   Move rate limit buckets and session storage to Redis to allow running multiple Gateway replicas in Kubernetes.

4.  **Database Migration**:
    *   Migrate `MerkleLogStore` from a local file to a proper database (Postgres) or a dedicated append-only log service for production persistence.

## 7. Conclusion

This repository represents a **high-quality security middleware** that is ready for deployment in environments requiring strict LLM governance. While there is some structural cleanup needed, the core value proposition—secure, verifiable, and fail-safe LLM gating—is fully implemented and tested.
