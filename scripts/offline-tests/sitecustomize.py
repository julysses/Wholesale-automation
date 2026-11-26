"""Fail closed on network access in Python test processes and their children."""
import os
import sys

os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def deny_network(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.sendto", "socket.getaddrinfo"}:
        raise RuntimeError(f"Offline test boundary blocked {event}; mock the provider")


sys.addaudithook(deny_network)
