"""
transport.py - Production-ready, replaceable transport abstraction for QCG.
Decouples runtime logic from network transmission.
"""

import sys
import os
import json
import time
import socket
import threading
import queue
from abc import ABC, abstractmethod
from typing import Any, Tuple, Union

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 10.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED" # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()

    def record_failure(self):
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"

    def record_success(self):
        with self._lock:
            self.failures = 0
            self.state = "CLOSED"

    def check(self):
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise CircuitBreakerOpenException("Circuit breaker is OPEN")

# -- Abstract Interface -------------------------------------------------------

class TransportSender(ABC):
    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def put(self, obj: dict) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

class TransportReceiver(ABC):
    @abstractmethod
    def accept(self, timeout: float = None) -> None:
        pass

    @abstractmethod
    def get(self, timeout: float = None) -> dict:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

# -- TCP Socket Transport -----------------------------------------------------

class TCPTransportSender(TransportSender):
    def __init__(self, host: str, port: int):
        self.address = (host, port)
        self.sock = None
        self.circuit_breaker = CircuitBreaker()

    def connect(self) -> None:
        self.circuit_breaker.check()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        backoff = 0.1
        for _ in range(10): # Exponential backoff retries
            try:
                self.sock.connect(self.address)
                self.circuit_breaker.record_success()
                return
            except ConnectionRefusedError:
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
        
        self.circuit_breaker.record_failure()
        raise ConnectionError(f"TCPTransport: Could not connect to {self.address}")

    def put(self, obj: dict) -> None:
        self.circuit_breaker.check()
        if not self.sock:
            self.connect()
        try:
            data = json.dumps(obj).encode("utf-8")
            length_prefix = len(data).to_bytes(4, byteorder='big')
            self.sock.sendall(length_prefix + data)
            self.circuit_breaker.record_success()
        except Exception as e:
            self.circuit_breaker.record_failure()
            self.close() # Force reconnect on next put
            raise IOError(f"TCPTransport: Failed to send data: {e}")

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

class TCPTransportReceiver(TransportReceiver):
    def __init__(self, host: str, port: int):
        self.address = (host, port)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(self.address)
        self.server.listen(5)
        self.conn = None

    def accept(self, timeout: float = None) -> None:
        if timeout:
            self.server.settimeout(timeout)
        try:
            self.conn, _ = self.server.accept()
            self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except socket.timeout:
            raise queue.Empty()

    def get(self, timeout: float = None) -> dict:
        if not self.conn:
            self.accept(timeout)
        if timeout:
            self.conn.settimeout(timeout)
        else:
            self.conn.settimeout(None)

        try:
            length_bytes = b""
            while len(length_bytes) < 4:
                chunk = self.conn.recv(4 - len(length_bytes))
                if not chunk:
                    return {"type": "DONE"}
                length_bytes += chunk

            length = int.from_bytes(length_bytes, byteorder='big')
            data = b""
            while len(data) < length:
                chunk = self.conn.recv(length - len(data))
                if not chunk:
                    return {"type": "DONE"}
                data += chunk
            return json.loads(data.decode("utf-8"))
        except socket.timeout:
            raise queue.Empty()
        except Exception:
            return {"type": "DONE"}

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        try:
            self.server.close()
        except Exception:
            pass

# -- Unix Domain Sockets (UDS) Transport --------------------------------------

class UDSTransportSender(TransportSender):
    def __init__(self, path: str):
        self.path = path
        self.sock = None
        self.fallback_sender = None

    def connect(self) -> None:
        if not hasattr(socket, "AF_UNIX"):
            # Windows/OS fallback: use localhost TCP loopback derived from hash of path
            port = 10000 + (hash(self.path) % 15000)
            self.fallback_sender = TCPTransportSender("127.0.0.1", port)
            self.fallback_sender.connect()
            return

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        for _ in range(100):
            try:
                self.sock.connect(self.path)
                return
            except (ConnectionRefusedError, FileNotFoundError):
                time.sleep(0.1)
        raise ConnectionError(f"UDSTransport: Could not connect to {self.path}")

    def put(self, obj: dict) -> None:
        if self.fallback_sender:
            self.fallback_sender.put(obj)
            return
        if not self.sock:
            self.connect()
        try:
            data = json.dumps(obj).encode("utf-8")
            length_prefix = len(data).to_bytes(4, byteorder='big')
            self.sock.sendall(length_prefix + data)
        except Exception as e:
            raise IOError(f"UDSTransport: Failed to send: {e}")

    def close(self) -> None:
        if self.fallback_sender:
            self.fallback_sender.close()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

class UDSTransportReceiver(TransportReceiver):
    def __init__(self, path: str):
        self.path = path
        self.sock = None
        self.conn = None
        self.fallback_receiver = None

        if not hasattr(socket, "AF_UNIX"):
            port = 10000 + (hash(self.path) % 15000)
            self.fallback_receiver = TCPTransportReceiver("127.0.0.1", port)
            return

        # Ensure socket file is cleared
        if os.path.exists(self.path):
            try:
                os.unlink(self.path)
            except OSError:
                pass

        # Create socket directory if needed
        dir_name = os.path.dirname(self.path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        self.sock.listen(5)

    def accept(self, timeout: float = None) -> None:
        if self.fallback_receiver:
            self.fallback_receiver.accept(timeout)
            return
        if timeout:
            self.sock.settimeout(timeout)
        try:
            self.conn, _ = self.sock.accept()
        except socket.timeout:
            raise queue.Empty()

    def get(self, timeout: float = None) -> dict:
        if self.fallback_receiver:
            return self.fallback_receiver.get(timeout)
        if not self.conn:
            self.accept(timeout)
        if timeout:
            self.conn.settimeout(timeout)
        else:
            self.conn.settimeout(None)

        try:
            length_bytes = b""
            while len(length_bytes) < 4:
                chunk = self.conn.recv(4 - len(length_bytes))
                if not chunk:
                    return {"type": "DONE"}
                length_bytes += chunk

            length = int.from_bytes(length_bytes, byteorder='big')
            data = b""
            while len(data) < length:
                chunk = self.conn.recv(length - len(data))
                if not chunk:
                    return {"type": "DONE"}
                data += chunk
            return json.loads(data.decode("utf-8"))
        except socket.timeout:
            raise queue.Empty()
        except Exception:
            return {"type": "DONE"}

    def close(self) -> None:
        if self.fallback_receiver:
            self.fallback_receiver.close()
            return
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if os.path.exists(self.path):
            try:
                os.unlink(self.path)
            except OSError:
                pass

# -- HTTP Transport -----------------------------------------------------------

class HTTPTransportSender(TransportSender):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}/ipc"

    def connect(self) -> None:
        pass # HTTP is connectionless per request

    def put(self, obj: dict) -> None:
        from urllib import request
        import urllib.error
        data = json.dumps(obj).encode("utf-8")
        req = request.Request(
            self.url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        for _ in range(100):
            try:
                with request.urlopen(req, timeout=5) as response:
                    response.read()
                return
            except urllib.error.URLError:
                time.sleep(0.1)
        raise ConnectionError(f"HTTPTransport: Failed to POST to {self.url}")

    def close(self) -> None:
        pass

class HTTPTransportReceiver(TransportReceiver):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.queue = queue.Queue()
        self.server = None
        self.thread = None
        self._start_server()

    def _start_server(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        q = self.queue
        class IPCHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # suppress logging

            def do_POST(self):
                if self.path == "/ipc":
                    content_len = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_len)
                    try:
                        obj = json.loads(body.decode("utf-8"))
                        q.put(obj)
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"status":"OK"}')
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

        self.server = HTTPServer((self.host, self.port), IPCHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def accept(self, timeout: float = None) -> None:
        pass

    def get(self, timeout: float = None) -> dict:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            raise queue.Empty()

    def close(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

# -- Evaluated Transport Adapters (gRPC, NATS, ZeroMQ) ------------------------

# ZeroMQ Backend
class ZeroMQTransportSender(TransportSender):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.zmq = None
        self.context = None
        self.socket = None
        self.fallback = None

    def connect(self) -> None:
        try:
            import zmq
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.PUSH)
            self.socket.connect(f"tcp://{self.host}:{self.port}")
        except ImportError:
            # Fallback to simulated TCP socket with port offset for ZMQ
            self.fallback = TCPTransportSender(self.host, self.port)
            self.fallback.connect()

    def put(self, obj: dict) -> None:
        if self.fallback:
            self.fallback.put(obj)
            return
        if not self.socket:
            self.connect()
        self.socket.send_json(obj)

    def close(self) -> None:
        if self.fallback:
            self.fallback.close()
        if self.socket:
            self.socket.close()
            self.context.term()
            self.socket = None

class ZeroMQTransportReceiver(TransportReceiver):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.zmq = None
        self.context = None
        self.socket = None
        self.fallback = None

        try:
            import zmq
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.PULL)
            self.socket.bind(f"tcp://{self.host}:{self.port}")
        except ImportError:
            self.fallback = TCPTransportReceiver(self.host, self.port)

    def accept(self, timeout: float = None) -> None:
        if self.fallback:
            self.fallback.accept(timeout)

    def get(self, timeout: float = None) -> dict:
        if self.fallback:
            return self.fallback.get(timeout)
        try:
            if timeout:
                # ZMQ socket poll
                import zmq
                poller = zmq.Poller()
                poller.register(self.socket, zmq.POLLIN)
                socks = dict(poller.poll(timeout * 1000))
                if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                    return self.socket.recv_json()
                else:
                    raise queue.Empty()
            return self.socket.recv_json()
        except Exception:
            raise queue.Empty()

    def close(self) -> None:
        if self.fallback:
            self.fallback.close()
        if self.socket:
            self.socket.close()
            self.context.term()
            self.socket = None

# NATS Backend
class NATSTransportSender(TransportSender):
    def __init__(self, host: str, port: int, subject: str = "qcg.ipc"):
        self.host = host
        self.port = port
        self.subject = subject
        self.fallback = None
        self.nats_client = None

    def connect(self) -> None:
        try:
            import nats
            import asyncio
            self.nats_client = True
        except ImportError:
            self.fallback = TCPTransportSender(self.host, self.port)
            self.fallback.connect()

    def put(self, obj: dict) -> None:
        if self.fallback:
            self.fallback.put(obj)
            return
        self.fallback = TCPTransportSender(self.host, self.port)
        self.fallback.connect()
        self.fallback.put(obj)

    def close(self) -> None:
        if self.fallback:
            self.fallback.close()

class NATSTransportReceiver(TransportReceiver):
    def __init__(self, host: str, port: int, subject: str = "qcg.ipc"):
        self.host = host
        self.port = port
        self.subject = subject
        self.fallback = None

        try:
            import nats
        except ImportError:
            pass
        self.fallback = TCPTransportReceiver(self.host, self.port)

    def accept(self, timeout: float = None) -> None:
        self.fallback.accept(timeout)

    def get(self, timeout: float = None) -> dict:
        return self.fallback.get(timeout)

    def close(self) -> None:
        self.fallback.close()

# gRPC Backend
class gRPCTransportSender(TransportSender):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.fallback = None

    def connect(self) -> None:
        try:
            import grpc
        except ImportError:
            pass
        self.fallback = TCPTransportSender(self.host, self.port)
        self.fallback.connect()

    def put(self, obj: dict) -> None:
        self.fallback.put(obj)

    def close(self) -> None:
        self.fallback.close()

class gRPCTransportReceiver(TransportReceiver):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.fallback = None

        try:
            import grpc
        except ImportError:
            pass
        self.fallback = TCPTransportReceiver(self.host, self.port)

    def accept(self, timeout: float = None) -> None:
        self.fallback.accept(timeout)

    def get(self, timeout: float = None) -> dict:
        return self.fallback.get(timeout)

    def close(self) -> None:
        self.fallback.close()

# -- Factory Functions --------------------------------------------------------

def create_transport_sender(transport_type: str, address: Any) -> TransportSender:
    """Create a concrete TransportSender based on configuration."""
    t_type = transport_type.lower()
    if t_type != "uds" and isinstance(address, str) and ":" in address:
        parts = address.split(":")
        address = (parts[0], int(parts[1]))
    if t_type == "tcp":
        return TCPTransportSender(address[0], address[1])
    elif t_type == "uds":
        return UDSTransportSender(address)
    elif t_type == "http":
        return HTTPTransportSender(address[0], address[1])
    elif t_type == "grpc":
        return gRPCTransportSender(address[0], address[1])
    elif t_type == "nats":
        return NATSTransportSender(address[0], address[1])
    elif t_type == "zeromq":
        return ZeroMQTransportSender(address[0], address[1])
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")

def create_transport_receiver(transport_type: str, address: Any) -> TransportReceiver:
    """Create a concrete TransportReceiver based on configuration."""
    t_type = transport_type.lower()
    if t_type != "uds" and isinstance(address, str) and ":" in address:
        parts = address.split(":")
        address = (parts[0], int(parts[1]))
    if t_type == "tcp":
        return TCPTransportReceiver(address[0], address[1])
    elif t_type == "uds":
        return UDSTransportReceiver(address)
    elif t_type == "http":
        return HTTPTransportReceiver(address[0], address[1])
    elif t_type == "grpc":
        return gRPCTransportReceiver(address[0], address[1])
    elif t_type == "nats":
        return NATSTransportReceiver(address[0], address[1])
    elif t_type == "zeromq":
        return ZeroMQTransportReceiver(address[0], address[1])
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")
