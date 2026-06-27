"""
web_server.py — Phase 4: Operational Readiness Endpoints

Provides a lightweight, production-grade HTTP API for TANTRA ecosystem integration.
Endpoints:
- GET /health         : Health, readiness, and metrics.
- GET /capabilities   : Capability manifest and API contracts.
- POST /verify        : Synchronous end-to-end integration flow.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from integration_harness import TANTRAIntegrationHarness
from integration_interfaces import CapabilityDiscoveryInterface

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Global harness instance
harness = TANTRAIntegrationHarness()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    pass

class OperationalReadinessHandler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        
    def do_GET(self):
        if self.path in ("/health", "/health/live", "/health/ready"):
            self._set_headers(200)
            health_data = harness.health_iface.get_health()
            self.wfile.write(json.dumps(health_data).encode("utf-8"))
            
        elif self.path == "/capabilities":
            self._set_headers(200)
            caps = CapabilityDiscoveryInterface.discover_capabilities()
            self.wfile.write(json.dumps(caps).encode("utf-8"))
            
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))
            
    def do_POST(self):
        if self.path == "/verify":
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Empty body"}).encode("utf-8"))
                return
                
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode('utf-8'))
            except Exception as e:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": f"Invalid JSON: {e}"}).encode("utf-8"))
                return
                
            contract_dict = payload.get("contract")
            pub_key = payload.get("producer_public_key")
            
            if not contract_dict or not pub_key:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Missing 'contract' or 'producer_public_key'"}).encode("utf-8"))
                return
                
            success, result = harness.process_incoming_contract(contract_dict, pub_key)
            status_code = 200 if success else 422
            self._set_headers(status_code)
            self.wfile.write(json.dumps(result).encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

def run_server(port=8080):
    server_address = ('', port)
    httpd = ThreadedHTTPServer(server_address, OperationalReadinessHandler)
    logging.info(f"Starting TANTRA Operational Readiness API on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        logging.info("Server stopped.")

if __name__ == "__main__":
    run_server()
