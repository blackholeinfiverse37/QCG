# Required Evidence Checklist

As an automated agent, I cannot take visual screenshots, but the system is fully configured to provide the required evidence. Please take the following manual screenshots from this working repository to complete the submission:

- [ ] `evidence/docker_running.png` -> Run `docker-compose up` and screenshot the healthy logs.
- [ ] `evidence/k8s_deployment.png` -> Run `kubectl get pods,svc -l app=qcg` and screenshot the output.
- [ ] `evidence/health_endpoint.png` -> Run `curl http://localhost:8080/health` and screenshot the JSON response.
- [ ] `evidence/capability_endpoint.png` -> Run `curl http://localhost:8080/capabilities` and screenshot the JSON response.
- [ ] `evidence/api_validation.png` -> Screenshot the passing `pytest tests/production_validation_suite.py` output.
- [ ] `evidence/replay_trust_consensus.png` -> Screenshot the `python tests/e2e_ecosystem_flow.py` terminal output showing the Replay, Trust, Execution, and Consensus stages all validating successfully.
- [ ] `evidence/load_testing.png` -> Run `locust -f load_testing/locustfile.py` and screenshot the web UI or CLI summary.
- [ ] `evidence/security_testing.png` -> Screenshot the passing `pytest tests/adversarial_tests.py` output.
