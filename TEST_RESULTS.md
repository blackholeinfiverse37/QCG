# Production Validation Evidence

Generated via `production_validation.py`.

### Cold Start & Health Check
```json
{
  "status": "UP",
  "version": "1.0.0",
  "readiness": "READY",
  "dependencies": {
    "replay_registry": "ONLINE",
    "consensus_nodes": "ONLINE"
  },
  "metrics": {
    "uptime_seconds": 8.73,
    "total_processed": 0,
    "error_rate": 0.0,
    "registry_size": 0
  }
}
```

### Capability Manifest
```json
{
  "owner": "QCG_TRUST_LAYER",
  "version": "1.0.0",
  "capabilities": [
    {
      "capability_id": "cap-replay-verif",
      "capability_name": "ReplayVerification",
      "scope": "SYSTEM",
      "status": "ACTIVE",
      "interface": {
        "inputs": [
          "message_id",
          "issued_at"
        ],
        "outputs": [
          "is_valid",
          "status",
          "sequence_number",
          "verification_hash"
        ]
      },
      "authority_limits": [
        "Occurrence registration",
        "Duplicate/stale rejection"
      ]
    },
    {
      "capability_id": "cap-trust-verif",
      "capability_name": "TrustVerification",
      "scope": "SYSTEM",
      "status": "ACTIVE",
      "interface": {
        "inputs": [
          "contract_dict"
        ],
        "outputs": [
          "passed",
          "halt_signal",
          "reason"
        ]
      },
      "authority_limits": [
        "Identity validation",
        "Signature check",
        "Role authorization"
      ]
    },
    {
      "capability_id": "cap-execution",
      "capability_name": "DeterministicExecution",
      "scope": "SYSTEM",
      "status": "ACTIVE",
      "interface": {
        "inputs": [
          "contract_dict"
        ],
        "outputs": [
          "ack",
          "runtime_hash",
          "contract_trace_id"
        ]
      },
      "authority_limits": [
        "Blind execution",
        "Result derivation"
      ]
    },
    {
      "capability_id": "cap-consensus",
      "capability_name": "ByzantineConsensus",
      "scope": "SYSTEM",
      "status": "ACTIVE",
      "interface": {
        "inputs": [
          "contract_dict",
          "producer_public_key"
        ],
        "outputs": [
          "consensus_reached",
          "agreement_percentage",
          "final_hash"
        ]
      },
      "authority_limits": [
        "Quorum calculation",
        "Node attestation"
      ]
    }
  ]
}
```

### Continuous Execution & Trace Continuity
```json
{
  "trace_id": "5d4f87ce-a72e-478f-96a8-2fd63968969e",
  "parent_trace_id": null,
  "flow_status": "COMPLETED",
  "stages": {
    "replay": {
      "is_valid": true,
      "status": "VALID",
      "sequence_number": 1,
      "verification_hash": "12ac74f467d45f6f266de4dba86176f5f23b0dc3bfa90b74a9be93741e07b556"
    },
    "trust": {
      "passed": true,
      "halt_signal": "",
      "reason": ""
    },
    "execution": {
      "contract_trace_id": "5d4f87ce-a72e-478f-96a8-2fd63968969e",
      "producer_type": "QUANTUM",
      "ack": "ACK:OK",
      "confidence": 0.99,
      "runtime_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b",
      "execution_timestamp": "2026-06-27T12:08:11.633630+00:00"
    },
    "consensus": {
      "participating_nodes": [
        "TANTRA_NODE_1",
        "TANTRA_NODE_2",
        "TANTRA_NODE_3"
      ],
      "final_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b",
      "agreement_percentage": 1.0,
      "consensus_reached": true,
      "disagreements": {},
      "consensus_round": 1,
      "quorum_size": 2,
      "node_attestations": {
        "TANTRA_NODE_1": {
          "node_id": "TANTRA_NODE_1",
          "agreement_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b",
          "status": "OK",
          "signature": "304502200c74d1022d547f703857fe1bdb07869b784dee80ccb45cc345b13397e7bfa94102210094b63e78f0dfb5e8a771ff6d4bcaed762a9e8b1ddc42013b833192f094e0a35b",
          "public_key": "3059301306072a8648ce3d020106082a8648ce3d03010703420004d6489d6087a50c2377ff8776a19257adc97939dd5027f065170baa573b9938a20d797cf155a811b7881e3f6ce6a378a90e18bef602a7a287e29278477ae5823e"
        },
        "TANTRA_NODE_2": {
          "node_id": "TANTRA_NODE_2",
          "agreement_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b",
          "status": "OK",
          "signature": "304402204d896534f5f356d1925f183772df9f66eae061f345373cf7ffa0e36c14253eed02202ddc78542bd02f46b17c0bf110c1793170672c1ee2bfcf95e578845f043e51a9",
          "public_key": "3059301306072a8648ce3d020106082a8648ce3d03010703420004954d1a449833f2f763b67dc2dc2761d115501013bb76081b86baa8a1f53dd4b398e904181fadbf9988fb76d360d17a51da009674bc43b167c4c449967a93d09d"
        },
        "TANTRA_NODE_3": {
          "node_id": "TANTRA_NODE_3",
          "agreement_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b",
          "status": "OK",
          "signature": "3046022100e6bc58b4115db094e3631669a23a48829eae2f50fb9b248cf012056f3363e686022100f8005e8aeb2b893075226c11ca70b51df0d6905b93e035fd4431b62e3a63f4ef",
          "public_key": "3059301306072a8648ce3d020106082a8648ce3d03010703420004995f1bf200b86b2013d49df47c57f290b58c2e158b2a5876ec3d442d9b4d32344cb3eafced7343a76afefa22efc271459730e95cb8b8620465f048061f354096"
        }
      },
      "consensus_timestamp": "2026-06-27T12:08:11.635380+00:00"
    }
  },
  "trace_continuity": {
    "sequence_number": 1,
    "runtime_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b",
    "final_hash": "71fa997c800971df51ee749b7d6252b150e82f4eb20490e63a0a28ffbdd4598b"
  }
}
```

### Replay Persistence (Duplicate Blocked)
```json
{
  "trace_id": "5d4f87ce-a72e-478f-96a8-2fd63968969e",
  "parent_trace_id": null,
  "flow_status": "HALTED",
  "stages": {
    "replay": {
      "is_valid": false,
      "status": "DUPLICATE",
      "sequence_number": 1,
      "verification_hash": null
    }
  },
  "halt_reason": "REPLAY_DUPLICATE"
}
```

### Failure Recovery (Signature Tamper)
```json
{
  "trace_id": "f67cb6b6-67ba-4ec3-a3ed-9f0c21d188fd",
  "parent_trace_id": null,
  "flow_status": "HALTED",
  "stages": {
    "replay": {
      "is_valid": true,
      "status": "VALID",
      "sequence_number": 2,
      "verification_hash": "b8899ab19d4126006eb111dc29fbb3e66100c57ce59e7dc21e115eb4ac622a0a"
    },
    "trust": {
      "passed": false,
      "halt_signal": "HALT:INVALID_SIGNATURE:ECDSA signature verification failed \u2014 contract may be tampered",
      "reason": "ECDSA signature verification failed \u2014 contract may be tampered"
    }
  },
  "halt_reason": "HALT:INVALID_SIGNATURE:ECDSA signature verification failed \u2014 contract may be tampered"
}
```

### Concurrent Execution (5 requests)
```json
{
  "status_codes": [
    200,
    200,
    200,
    200,
    200
  ]
}
```
