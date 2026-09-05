"""PyInstaller runtime hook: point TLS at the bundled certifi CA store.

In a frozen binary the system trust store may be unavailable; certifi is
bundled and its path is exported so both httpx and the raw ssl transport
verify certificates correctly.
"""

import os
import sys

if getattr(sys, "frozen", False):
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except Exception:
        pass
