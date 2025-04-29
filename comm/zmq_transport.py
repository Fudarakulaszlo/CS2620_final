"""comm/zmq_transport.py

ZeroMQ‑based broadcast transport used by *distributed_consensus* agents.

Each agent exposes **exactly one** PUB socket and maintains **exactly one**
SUB socket that connects to every neighbour’s PUB endpoint.  This file
wraps that pattern in a tiny Python class so that switching to a different
backend (UDP multicast, nanomsg, etc.) becomes a ~100‑line drop‑in
replacement without touching the algorithm layer.

Design goals
------------
* No `asyncio` dependency – agents run a simple, fast time‑slot loop.
* Non‑blocking receive so we can harvest all messages until a deadline.
* Automatic context teardown – when the process exits, sockets close.
* Minimal footprint – ~70 LOC including docstrings & typing.

Example
~~~~~~~
>>> t = ZmqTransport(pub_port=5556,
...                  neigh_endpoints=["tcp://127.0.0.1:5557"])  # doctest: +SKIP
>>> t.send(b"hello")
>>> msg = t.recv_nowait()
>>> t.close()
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from typing import List, Optional

import zmq

__all__ = ["ZmqTransport", "build_endpoint"]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def build_endpoint(host: str, port: int) -> str:
    """Return a TCP ZeroMQ endpoint string for the given host/port."""
    return f"tcp://{host}:{port}"


# ---------------------------------------------------------------------------
# Main transport class
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ZmqTransport:
    """Thin wrapper around ZeroMQ PUB/SUB for one agent.

    Parameters
    ----------
    pub_port:
        Local TCP port this agent will **bind** its PUB socket to.
    neigh_endpoints:
        Iterable of TCP endpoints (\*tcp://host:port\*) that the SUB socket
        should connect to – usually the neighbours’ PUB addresses.
    ctx:
        Optionally reuse an existing ``zmq.Context``.  If ``None`` the class
        creates and owns its own singleton context.
    host:
        Local host/interface to bind the PUB socket (default ``"127.0.0.1"``).
    """

    pub_port: int
    neigh_endpoints: List[str]
    ctx: Optional[zmq.Context] = None
    host: str = "127.0.0.1"

    # internal fields (created in __post_init__)
    _pub_socket: zmq.Socket | None = None
    _sub_socket: zmq.Socket | None = None

    # ---------------------------------------------------------------------
    # Construction & teardown
    # ---------------------------------------------------------------------

    def __post_init__(self) -> None:  # noqa: D401 – standard dataclass hook
        if self.ctx is None:
            # One context per process is recommended.  We don’t enforce the
            # singleton, but we strongly hint via an env variable.
            self.ctx = zmq.Context.instance()

        # PUB socket – bind once.
        self._pub_socket = self.ctx.socket(zmq.PUB)
        self._pub_socket.setsockopt(zmq.LINGER, 0)
        pub_endpoint = build_endpoint(self.host, self.pub_port)
        self._pub_socket.bind(pub_endpoint)
        log.debug("PUB bound to %s", pub_endpoint)

        # SUB socket – connect to all neighbours.
        self._sub_socket = self.ctx.socket(zmq.SUB)
        self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")  # subscribe ALL
        self._sub_socket.setsockopt(zmq.LINGER, 0)
        for ep in self.neigh_endpoints:
            # Skip self‑connect, but it’s harmless if we don’t.
            if ep.endswith(f":{self.pub_port}"):
                continue
            self._sub_socket.connect(ep)
            log.debug("SUB connected to %s", ep)

        # small sanity check – warn if no peers (lonely agent)
        if not self.neigh_endpoints:
            log.warning("Agent on port %d has no neighbour endpoints", self.pub_port)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        """Broadcast ``data`` (non‑blocking).  Drops if the inproc buffer is full."""
        assert self._pub_socket is not None
        try:
            self._pub_socket.send(data, zmq.NOBLOCK)
        except zmq.Again:
            # PUB sockets drop when HWM is reached – we silently log and move on
            log.warning("PUB buffer full – dropped message (%d bytes)", len(data))

    def recv_nowait(self) -> Optional[bytes]:
        """Return the next message if available, else ``None`` (non‑blocking)."""
        assert self._sub_socket is not None
        try:
            return self._sub_socket.recv(zmq.NOBLOCK)
        except zmq.Again:
            return None

    # ------------------------------------------------------------------
    # Cleanup helpers (idempotent)
    # ------------------------------------------------------------------

    def close(self) -> None:  # noqa: D401 – not a property
        """Close sockets (safe to call multiple times)."""
        if self._pub_socket is not None:
            self._pub_socket.close(0)
            self._pub_socket = None
        if self._sub_socket is not None:
            self._sub_socket.close(0)
            self._sub_socket = None

    # Automatic cleanup for context manager usage
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # noqa: D401 – context manager magic
        self.close()

    # Destructor safety net – if user forgot to close explicitly.
    def __del__(self):
        # Don’t raise inside __del__.
        try:
            self.close()
        except Exception:
            pass
