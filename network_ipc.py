import socket
import json
import time

class IPCSender:
    def __init__(self, host="127.0.0.1", port=9001):
        self.address = (host, port)
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for _ in range(100):
            try:
                self.sock.connect(self.address)
                return
            except ConnectionRefusedError:
                time.sleep(0.1)
        raise ConnectionError(f"Could not connect to {self.address}")

    def put(self, obj):
        if not self.sock:
            self.connect()
        try:
            data = json.dumps(obj).encode("utf-8")
            length_prefix = len(data).to_bytes(4, byteorder='big')
            self.sock.sendall(length_prefix + data)
        except Exception:
            pass # Ignore errors on send

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

class IPCReceiver:
    def __init__(self, host="127.0.0.1", port=9001):
        self.address = (host, port)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(self.address)
        self.server.listen(1)
        self.conn = None

    def accept(self, timeout=None):
        if timeout:
            self.server.settimeout(timeout)
        self.conn, _ = self.server.accept()

    def get(self, timeout=None):
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
            import queue
            raise queue.Empty()
        except Exception:
            return {"type": "DONE"}

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        try:
            self.server.close()
        except Exception:
            pass

import threading

def start_heartbeat_server(port):
    def serve():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", port))
            server.listen(1)
            while True:
                conn, _ = server.accept()
                data = conn.recv(1024)
                if b"PING" in data:
                    conn.sendall(b"PONG")
                conn.close()
        except Exception:
            pass
        finally:
            server.close()
            
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return t

def check_heartbeat(port, timeout=1.0):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", port))
        sock.sendall(b"PING")
        data = sock.recv(1024)
        sock.close()
        return b"PONG" in data
    except Exception:
        return False
