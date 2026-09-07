"""Collection importers: turn an API spec into replayable RequestConfigs.

Each importer is a pure function ``spec -> list[RequestConfig]`` with no network
and no new mandatory dependency (OpenAPI YAML uses the already-required
``pyyaml``; Postman is plain JSON). Requests that have no example carry a
``FUZZ`` marker so they drop straight into the fuzzer.
"""

from curlcommander.core.importers.openapi import SpecImportError, parse_openapi
from curlcommander.core.importers.postman import parse_postman

__all__ = ["SpecImportError", "parse_openapi", "parse_postman"]
