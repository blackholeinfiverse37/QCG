# Discovery API Documentation

## Base URL

```
http://{host}:{port}/platform/v1/
```

Default: `http://127.0.0.1:9010/platform/v1/`

---

## Service Discovery Endpoints

### List All Services

```
GET /platform/v1/services
```

**Response (200):**
```json
{
  "services": [ { ...PlatformServiceRecord... } ],
  "count": 2,
  "registry_version": "1.0.0"
}
```

### Fetch Service by ID

```
GET /platform/v1/services/{service_id}
```

**Response (200):** Full `PlatformServiceRecord` as JSON.

**Response (404):** `{"error": "Service 'id' not found"}`

### Fetch Versions

```
GET /platform/v1/services/{service_id}/versions
```

**Response (200):**
```json
{
  "service_id": "TANTRA-PSR-USF-001",
  "compatible": ["1.0.0"],
  "deprecated": ["0.9.0"],
  "unsupported": ["0.1.0"]
}
```

### Fetch Metadata

```
GET /platform/v1/services/{service_id}/metadata
```

**Response (200):**
```json
{
  "service": { ...PlatformServiceRecord... },
  "manifest": { ...CapabilityManifest... },
  "versions": { ...VersionMatrix... }
}
```

### Fetch Contracts

```
GET /platform/v1/services/{service_id}/contracts
```

**Response (200):**
```json
{
  "service_id": "TANTRA-PSR-USF-001",
  "contracts": [ { ...OperationContract... } ],
  "count": 3
}
```

### Fetch Endpoints

```
GET /platform/v1/services/{service_id}/endpoints
```

**Response (200):**
```json
{
  "service_id": "TANTRA-PSR-USF-001",
  "endpoints": {
    "execution": "http://...",
    "health": "http://...",
    "readiness": "http://...",
    "metrics": "http://...",
    "evidence": "http://...",
    "version": "http://...",
    "capability": "http://..."
  }
}
```

### Fetch Health

```
GET /platform/v1/services/{service_id}/health
```

**Response (200):**
```json
{
  "status": "UP",
  "service_id": "TANTRA-PSR-USF-001",
  "service_status": "ACTIVE",
  "version": "1.0.0",
  "registration_timestamp": "ISO-8601"
}
```

### Fetch Compatibility

```
GET /platform/v1/services/{service_id}/compatibility
```

**Response (200):**
```json
{
  "service_id": "TANTRA-PSR-USF-001",
  "current_version": "1.0.0",
  "version_matrix": { "compatible": [...], "deprecated": [...], "unsupported": [...] },
  "runtime_type": "PROCESS",
  "capability_category": "OPTIMIZATION"
}
```

---

## Server Management Endpoints

### Health

```
GET /platform/v1/health
```

**Response (200):**
```json
{
  "status": "UP",
  "version": "1.0.0",
  "uptime_seconds": 123.45,
  "total_requests": 42,
  "registry_version": "1.0.0"
}
```

### Readiness

```
GET /platform/v1/readiness
```

**Response (200):**
```json
{
  "ready": true,
  "services_registered": 2,
  "version": "1.0.0"
}
```

### Metrics (Prometheus)

```
GET /platform/v1/metrics
```

**Response (200, text/plain):**
```
# HELP tantra_platform_uptime_seconds Discovery server uptime
# TYPE tantra_platform_uptime_seconds gauge
tantra_platform_uptime_seconds 123.45
# HELP tantra_platform_requests_total Total requests to discovery server
# TYPE tantra_platform_requests_total counter
tantra_platform_requests_total 42
...
```

### Evidence

```
GET /platform/v1/evidence
```

**Response (200):**
```json
{
  "evidence": [ { ...RegistrationEvidence... } ],
  "chain_length": 12,
  "chain_valid": true,
  "head_hash": "sha256..."
}
```

### Version

```
GET /platform/v1/version
```

**Response (200):**
```json
{
  "discovery_server_version": "1.0.0",
  "registry_version": "1.0.0",
  "api_version": "v1"
}
```

---

## Version Negotiation

### Negotiate Version

```
POST /platform/v1/negotiate
```

**Request:**
```json
{
  "service_id": "TANTRA-PSR-USF-001",
  "requested_version": "1.0.0"
}
```

**Response (200) - Compatible:**
```json
{
  "status": "COMPATIBLE",
  "requested_version": "1.0.0",
  "service_id": "TANTRA-PSR-USF-001",
  "message": "Version 1.0.0 is fully supported.",
  "negotiated_version": "1.0.0",
  "timestamp": "ISO-8601"
}
```

**Response (200) - Deprecated:**
```json
{
  "status": "DEPRECATED",
  "message": "Version 0.9.0 is deprecated. Please migrate to 1.0.0.",
  "negotiated_version": "0.9.0",
  "suggested_versions": ["1.0.0"]
}
```

**Response (200) - Unsupported:**
```json
{
  "status": "UNSUPPORTED",
  "message": "Version 0.1.0 is no longer supported. Request rejected.",
  "negotiated_version": null,
  "suggested_versions": ["1.0.0"]
}
```

---

## Error Responses

| Code | Description |
|---|---|
| 400 | Invalid request body or missing parameters |
| 404 | Service or endpoint not found |
