"""
test_distributed_runtime.py - Integration and unit tests for QCG Distributed Runtime.
"""

import os
import time
import unittest
import tempfile
from pathlib import Path

import config
from transport import (
    create_transport_sender,
    create_transport_receiver,
    TCPTransportSender,
    HTTPTransportSender,
    UDSTransportSender
)
from capability_registry import (
    CapabilityRegistryServer,
    CapabilityRegistryClient,
    validate_capability_payload
)
from observability import TraceStore, TraceEntry

class TestDistributedTransport(unittest.TestCase):
    def test_tcp_transport_loopback(self):
        port = 12345
        receiver = create_transport_receiver("tcp", ("127.0.0.1", port))
        sender = create_transport_sender("tcp", ("127.0.0.1", port))

        sender.connect()
        test_payload = {"hello": "world", "type": "TEST"}
        sender.put(test_payload)
        
        received = receiver.get(timeout=2.0)
        self.assertEqual(received["hello"], "world")
        
        sender.close()
        receiver.close()

    def test_http_transport_loopback(self):
        port = 12346
        receiver = create_transport_receiver("http", ("127.0.0.1", port))
        sender = create_transport_sender("http", ("127.0.0.1", port))

        test_payload = {"greeting": "hello http", "type": "TEST"}
        sender.put(test_payload)
        
        received = receiver.get(timeout=3.0)
        self.assertEqual(received["greeting"], "hello http")
        
        receiver.close()

    def test_uds_transport_fallback_or_native(self):
        uds_path = "./logs/test_uds.sock"
        receiver = create_transport_receiver("uds", uds_path)
        sender = create_transport_sender("uds", uds_path)

        sender.connect()
        test_payload = {"uds_msg": "testing UDS", "type": "TEST"}
        sender.put(test_payload)
        
        received = receiver.get(timeout=2.0)
        self.assertEqual(received["uds_msg"], "testing UDS")
        
        sender.close()
        receiver.close()

class TestCapabilityRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_port = 12390
        cls.server = CapabilityRegistryServer("127.0.0.1", cls.registry_port)
        cls.server.start()
        time.sleep(0.5)
        cls.client = CapabilityRegistryClient(f"http://127.0.0.1:{cls.registry_port}")

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_schema_validation(self):
        # Invalid payload (missing capability_id)
        invalid_payload = {
            "capability_name": "REPLAY_ENFORCEMENT",
            "version": "1.0.0"
        }
        valid, err = validate_capability_payload(invalid_payload)
        self.assertFalse(valid)
        self.assertIn("Missing required key", err)

        # Valid payload
        valid_payload = {
            "capability_id": "a1b2c3d4-e5f6-5a7b-8c9d-0e1f2a3b4c5d",
            "capability_name": "REPLAY_ENFORCEMENT",
            "owner": {"team": "infra", "contact": "infra@bhiv"},
            "version": "1.0.0",
            "status": "ACTIVE",
            "scope": "SYSTEM",
            "dependencies": [],
            "attachment_rules": {"attachment_type": "embedded", "protocol": "in_process"},
            "authority_limits": {"owns": ["seq"], "does_not_own": ["exec"]},
            "inputs": [],
            "outputs": [],
            "consumers": [],
            "documentation_reference": {"primary": "ref.md"}
        }
        valid, err = validate_capability_payload(valid_payload)
        self.assertTrue(valid)

    def test_dynamic_register_and_discover(self):
        cap_id = "f6a7b8c9-d0e1-5f2a-8b3c-4d5e6f7a8b9c"
        payload = {
            "capability_id": cap_id,
            "capability_name": "BYZANTINE_CONSENSUS_TEST",
            "owner": {"team": "consensus-team", "contact": "consensus@bhiv"},
            "version": "1.0.0",
            "status": "ACTIVE",
            "scope": "SYSTEM",
            "dependencies": [],
            "attachment_rules": {"attachment_type": "api_linked", "protocol": "tcp", "endpoint": "127.0.0.1:9005"},
            "authority_limits": {"owns": ["quorum"], "does_not_own": ["signing"]},
            "inputs": [],
            "outputs": [],
            "consumers": [],
            "documentation_reference": {"primary": "consensus.md"}
        }
        
        reg_ok = self.client.register(payload)
        self.assertTrue(reg_ok)

        discovered = self.client.discover("BYZANTINE_CONSENSUS_TEST")
        self.assertIsNotNone(discovered)
        self.assertEqual(discovered["capability_id"], cap_id)
        self.assertEqual(discovered["attachment_rules"]["endpoint"], "127.0.0.1:9005")

class TestOpenTelemetryObservability(unittest.TestCase):
    def test_otel_span_export(self):
        store = TraceStore()
        trace_id = "test-otel-trace-123"
        store.record_execution_trace(
            trace_id=trace_id,
            contract_hash="abc",
            ack="ACK:OK",
            runtime_hash="xyz",
            confidence=0.95
        )
        
        spans = store.export_opentelemetry(trace_id)
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span["name"], "qcg:execution")
        self.assertEqual(span["attributes"]["qcg.data.ack"], "ACK:OK")
        self.assertEqual(span["status"]["code"], "STATUS_CODE_OK")
        self.assertTrue("traceId" in span)
        self.assertTrue("spanId" in span)

if __name__ == "__main__":
    unittest.main()
