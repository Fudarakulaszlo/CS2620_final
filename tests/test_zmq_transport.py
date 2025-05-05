"""
A lightweight, socket-level smoke test for the ZeroMQ transport wrapper.

We use *inproc://* (shared memory) so no real TCP ports are allocated,
making the test fast and flaky-free.
"""
import random
import time

import pytest
import zmq

from comm.zmq_transport import ZmqTransport


@pytest.fixture(scope="module")
def ctx():
    """Re-use one global Context to save resources."""
    yield zmq.Context.instance()


def test_inproc_echo(ctx):
    # unique endpoint for this run
    endpoint = f"inproc://test-{random.randint(0, 1<<30)}"

    pub = ctx.socket(zmq.PUB)
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")

    pub.bind(endpoint)
    sub.connect(endpoint)

    # let the SUB subscribe before we send
    time.sleep(0.05)

    msg = b"hello"
    pub.send(msg)

    deadline = time.time() + 1.0  # 1 s timeout
    while time.time() < deadline:
        try:
            received = sub.recv(flags=zmq.NOBLOCK)
            assert received == msg
            break
        except zmq.Again:
            time.sleep(0.01)
    else:
        pytest.fail("PUB/SUB message not received within 1 s")
