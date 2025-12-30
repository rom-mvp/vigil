# Security

This project enforces fail-closed SaaS controls and signed auditability for AgentShield-integrated traffic.

- Fail-closed enforcement: critical integration coverage in tests/integration/test_fail_closed.py.
- Merkle audit chain integrity: tamper detection in tests/integration/test_merkle_audit_chain.py.
- Decision signing: AgentShield decisions are signed (schema version `as_decision_v1`) and verified in src/vigil/agentshield_client.py.

## Running the critical checks

```bash
python -m pytest tests/integration/test_fail_closed.py tests/integration/test_merkle_audit_chain.py -v --tb=short
```
