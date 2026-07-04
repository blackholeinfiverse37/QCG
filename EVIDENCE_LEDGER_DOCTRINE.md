# Evidence Ledger Constitutional Doctrine

The Evidence Ledger is a foundational infrastructure component designed to provide a constitutionally bounded, replay-safe, and ecosystem-ready trust capability across BHIV systems. Its core purpose is to prove execution lineage and evidentiary integrity without enforcing governance or operational validity.

## 1. Authority Owned

The Evidence Ledger has strictly defined responsibilities. It **MAY**:
- **Store evidence**: Persist execution records securely.
- **Chain evidence**: Link execution records sequentially to create immutable lineage.
- **Generate Merkle roots**: Compute a unified State Hash (Merkle root) for a given point in time across the evidence tree.
- **Generate inclusion proofs**: Provide verifiable proofs that a specific piece of execution evidence exists within the ledger at a certain state.
- **Expose evidence snapshots**: Serve point-in-time reference states of the ledger back to ecosystem callers for cross-validation or verification.

## 2. Authority Explicitly NOT Owned

To preserve the separation of concerns and avoid entrenchment of validation systems, the Evidence Ledger **MUST NOT**:
- **Authorize execution**: The ledger cannot decide if an execution was permitted to run.
- **Approve execution**: The ledger cannot assert if an execution was correct or met operational guidelines.
- **Reject execution**: The ledger cannot block execution ingestion based on rule violations (unless the cryptographic chain itself is invalid).
- **Validate governance legitimacy**: The ledger is completely ignorant of whether the producer met the ecosystem's policy constitution (GC boundary).
- **Create replay verdicts**: Replay validation is the domain of the Replay Authority; the ledger only provides the lineage.
- **Create constitutional truth**: Evidence is solely a record of *what happened*, not *what should have happened*.

## 3. Layer Placement

The Evidence Ledger acts as the persistence and chaining bedrock of the overall Execution Evidence system.

* **Ecosystem Layer**: Transverse Data / Infrastructure (Positioned alongside TMS, but fully insulated from application-level business logic).
* **Upstream Systems**: 
  - **Execution Runtime**: Produces the ExecutionRecords during raw processing.
  - **Kanishk Optimization Runtime**: Can feed deterministic optimization executions as upstream evidence.
  - **Canonical Replay Authority**: Reads the chain to reconstruct and guarantee lineage mapping.
* **Downstream Systems**:
  - **Constitutional Review (GC)**: Connects to ingest proofs that validations occurred (without ledger owning the legitimacy result).
  - **Data Review (MDU)**: Audits the chain for provenance ownership and replay lineage.

## 4. Ownership and Authority Matrices

### 4.1 Ownership Matrix

| Asset / Capability | Owner | Scope |
| :--- | :--- | :--- |
| **ExecutionRecord Storage** | Evidence Ledger | Persistence and retrievability of raw records. |
| **Evidence Schema** | MDU | Defining what a valid execution payload looks like. |
| **Provenance Lineage** | MDU / Evidence Ledger | Chain custody of sequential executions. |
| **Execution Authorization** | Governance (GC) | Policy rules determining right to execute. |

### 4.2 Authority Matrix

| Action | Authorized Entity | Verification Artifact |
| :--- | :--- | :--- |
| **Submit Evidence** | Execution Runtime / Providers | Valid ExecutionRecord |
| **Request Merkle Proof** | Any Ecosystem Consumer | Inclusion Proof (JSON) |
| **Reconstruct Timeline** | Replay Authority | Ledger Snapshot + Reference ID |
| **Validate Legitimacy** | Constitutional Review (GC) | Governance Verdict (Independent) |

### 4.3 Negative Authority Matrix

| Forbidden Action | Entity Denied | Enforcing Mechanism |
| :--- | :--- | :--- |
| **Reject unapproved execution** | Evidence Ledger | Ledger ingests purely on cryptographic chain validity; business rules are ignored. |
| **Assert governance failure** | Evidence Ledger | The ledger only knows hashes; it does not parse policy failures. |
| **Modify historical evidence** | Any System (Including Ledger) | Cryptographic chaining (Previous Hash binding). |

## 5. Lifecycle Diagram

```mermaid
sequenceDiagram
    participant R as Execution Runtime
    participant EL as Evidence Ledger
    participant RA as Replay Authority
    participant MDU as Data Review (MDU)
    participant GC as Constitutional Review

    R->>R: Execute Workload
    R->>EL: Submit ExecutionRecord
    Note over EL: Compute Hash Pair<br/>Update Merkle Tree<br/>Chain Evidence
    EL-->>R: Return LedgerSnapshot (w/ Merkle Root)
    
    RA->>EL: Query Previous Execution Lineage
    EL-->>RA: Provide Execution Chain
    Note over RA: Replay Computation<br/>Evaluate Replay Verdict
    
    GC->>EL: Request Inclusion Proof for Record
    EL-->>GC: Return Proof Path & Siblings
    MDU->>EL: Audit Sequence and Provenance
    Note over GC,MDU: Independent Governance & Trust Verification
```

## 6. Runtime Example

1. **Producer Side**: The Edge Runtime processes a quantum optimization scenario (Kanishk). It generates an `ExecutionRecord` carrying `runtime_hash` and `execution_hash`.
2. **Ledger Ingestion**: The Edge Runtime calls the Evidence Ledger API to push the record. The Ledger performs a lightweight cryptographic validation: `hash_pair(current_head, new_record.execution_hash)`.
3. **Chain Advancement**: The Ledger stores the record, updates its internal state hash, and returns a `LedgerSnapshot`.
4. **Third-Party Verification**: Later, the Constitutional Review node (GC) is asked to validate that this execution met policy. Before evaluating the policy, GC requests a Merkle Inclusion Proof from the Evidence Ledger for the specific `execution_hash` to prove it canonically exists in the timeline, prior to applying its own legitimacy check.
