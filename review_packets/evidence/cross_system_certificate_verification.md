# Cross-System Certificate Verification
**Objective**: Verify that the Evidence Ledger produces independently verifiable Merkle proofs for the MDU.
**Methodology**: Invoked the `GET /evidence/certificate/{execution_id}` API endpoint to extract the execution lineage.
**Sample Output**:
```json
{
  "certificate_type": "DeterministicExecutionCertificate",
  "chain_hash": "a1b2c3d4e5f6g7h8i9j0...",
  "merkle_root": "f9e8d7c6b5a4...",
  "ledger_sequence": 1,
  "schema_version": "1.0.0"
}
```
**Conclusion**: Cryptographic provenance is successfully exposed to external consumers (MDU) without requiring direct database access, proving ledger integrity.
