# Version Negotiation Guide

## Overview

TANTRA Platform Services support deterministic version negotiation to ensure sovereign consumers can safely interact with capabilities without hardcoding brittle assumptions.

The `VersionNegotiator` maintains a compatibility matrix for each service and provides graceful rejection or deprecation warnings when unsupported versions are requested.

---

## The Version Matrix

Every registered Platform Service must define a version matrix during registration:

- **Compatible:** Fully supported versions that are safe to consume.
- **Deprecated:** Versions that are still functional but should be migrated away from. Consumers using these will receive a `DEPRECATED` response with suggested alternatives.
- **Unsupported:** Versions that have been explicitly removed or banned. Consumers using these will be rejected.

---

## Negotiation Protocol

### 1. Consumer Request

A consumer sends a POST request to the discovery server's negotiation endpoint:

```http
POST /platform/v1/negotiate
Content-Type: application/json

{
  "service_id": "TANTRA-PSR-USF-001",
  "requested_version": "1.0.0"
}
```

### 2. Provider Evaluation

The `VersionNegotiator` evaluates the `requested_version` against the service's compatibility matrix:

1. If in `compatible` list → Return `COMPATIBLE`
2. If in `deprecated` list → Return `DEPRECATED`
3. If in `unsupported` list → Return `UNSUPPORTED`
4. If not found in any list → Return `UNSUPPORTED` (graceful rejection)

### 3. Response States

#### COMPATIBLE

The version is fully supported. The consumer can proceed with execution.

```json
{
  "status": "COMPATIBLE",
  "requested_version": "1.0.0",
  "service_id": "TANTRA-PSR-USF-001",
  "message": "Version 1.0.0 is fully supported.",
  "negotiated_version": "1.0.0",
  "timestamp": "2026-07-24T08:00:00Z"
}
```

#### DEPRECATED

The version works, but the consumer is strongly advised to migrate. A `suggested_versions` list is provided.

```json
{
  "status": "DEPRECATED",
  "requested_version": "0.9.0",
  "service_id": "TANTRA-PSR-USF-001",
  "message": "Version 0.9.0 is deprecated. Please migrate to 1.0.0.",
  "negotiated_version": "0.9.0",
  "suggested_versions": ["1.0.0"],
  "timestamp": "2026-07-24T08:00:00Z"
}
```

#### UNSUPPORTED

The version cannot be used. The consumer must abort execution. A `suggested_versions` list is provided to help the consumer upgrade.

```json
{
  "status": "UNSUPPORTED",
  "requested_version": "0.1.0",
  "service_id": "TANTRA-PSR-USF-001",
  "message": "Version 0.1.0 is no longer supported. Request rejected.",
  "negotiated_version": null,
  "suggested_versions": ["1.0.0"],
  "timestamp": "2026-07-24T08:00:00Z"
}
```

#### UNKNOWN_SERVICE

The requested service is not registered in the negotiation system.

```json
{
  "status": "UNKNOWN_SERVICE",
  "requested_version": "1.0.0",
  "service_id": "NONEXISTENT",
  "message": "Service 'NONEXISTENT' is not registered for version negotiation.",
  "suggested_versions": [],
  "timestamp": "2026-07-24T08:00:00Z"
}
```

---

## Evidence Generation

Every version negotiation request generates a replay-safe evidence record on the provider side. This creates an audit trail of which consumers are requesting which versions, enabling data-driven deprecation cycles.

Event type: `VERSION_NEGOTIATION`

```json
{
  "requested_version": "0.9.0",
  "negotiation_status": "DEPRECATED",
  "negotiated_version": "0.9.0"
}
```
