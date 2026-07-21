# TMS: Threat Modeling & Security

This document outlines the Threat Modeling & Security (TMS) posture for the Universal Solver Fabric.

## 1. Isolation & Determinism
The execution adapter (`execution_adapter.py`) strictly enforces isolation between the fabric and underlying solvers. External solver execution is assumed to be untrusted; therefore, all outputs are normalized before being passed back up to the Platform Service.

## 2. Replay Integrity
All execution requests produce deterministic `trace_id` and `replay_id` artifacts. These ensure that runtime evidence cannot be forged and can be deterministically reproduced to prove execution integrity.

## 3. Capability Spoofing
The `solver_contract.schema.json` strictly validates solver registrations. Solvers cannot declare capabilities they don't possess (e.g. deterministic execution) without being explicitly filtered or failing post-execution trace validation.
