# Quantum Communication Gateway (QCG) Deployment Guide

This guide details the steps to deploy the QCG ecosystem service into a production Kubernetes cluster. The service is packaged as a scalable Docker container and uses Kubernetes for orchestration.

## Prerequisites

1. Kubernetes Cluster (v1.24+ recommended)
2. `kubectl` CLI configured with cluster access
3. Docker or Podman for local image builds
4. Container Registry (e.g., Docker Hub, AWS ECR, GCP GCR) to push the Docker image

## 1. Container Packaging

QCG is packaged as an optimized, multi-stage Docker container. 

To build the image:
```bash
docker build -t your-registry/qcg-service:latest .
```

To run it locally via Docker Compose (for testing):
```bash
docker-compose up --build
```
This will start the service on `http://localhost:8080`.

## 2. Pushing to Registry

Before deploying to Kubernetes, push the built image to your container registry:
```bash
docker push your-registry/qcg-service:latest
```

## 3. Kubernetes Deployment

The configuration for Kubernetes resides in the `k8s/` directory. By default, it configures:
- A scalable Deployment with a minimum of 3 replicas.
- A LoadBalancer Service for external traffic routing.
- Resource constraints, readiness, and liveness probes.

### Update the Image Reference
Edit `k8s/deployment.yaml` and replace the `image:` placeholder with your registry path:
```yaml
      containers:
      - name: qcg-server
        image: your-registry/qcg-service:latest
```

### Apply Kubernetes Manifests

Apply the deployment and service manifests:
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## 4. Operational Validation

Once deployed, verify the pods are running and healthy:
```bash
kubectl get pods -l app=qcg
```

Check the health endpoint. Replace `<EXTERNAL-IP>` with the IP allocated to the `qcg-service` LoadBalancer.
```bash
curl http://<EXTERNAL-IP>:8080/health
```

Expected Response:
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
    "uptime_seconds": 120.45,
    "total_processed": 0,
    "error_rate": 0.0,
    "registry_size": 0
  }
}
```

## 5. Scaling

To manually scale the deployment:
```bash
kubectl scale deployment qcg-deployment --replicas=5
```

Alternatively, configure a Horizontal Pod Autoscaler (HPA) to automatically scale based on CPU or memory usage.

## 6. Logs & Telemetry

QCG uses structured JSON logging. You can view logs natively via `kubectl`:
```bash
kubectl logs -f deployment/qcg-deployment
```

For production, it is recommended to ingest these JSON logs into your central telemetry systems (e.g., ElasticSearch, Datadog, or Grafana Loki).
