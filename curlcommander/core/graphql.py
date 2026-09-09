"""GraphQL helper utilities: Introspection schema parsing and request builder."""

from __future__ import annotations

import json
from typing import Any

from curlcommander.core.request_model import RequestConfig

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields {
        name
        description
        args {
          name
          type { name kind ofType { name kind } }
        }
        type { name kind ofType { name kind } }
      }
    }
  }
}
"""


def build_graphql_request(
    url: str,
    query: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
) -> RequestConfig:
    """Construct a POST RequestConfig with a GraphQL JSON payload."""
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    if operation_name:
        payload["operationName"] = operation_name

    body_json = json.dumps(payload, indent=2)

    return RequestConfig(
        method="POST",
        url=url,
        body=body_json,
        body_type="json",
        headers={"Content-Type": "application/json"},
    )


def extract_operations(introspection_data: dict[str, Any]) -> dict[str, list[str]]:
    """Extract query and mutation field names from GraphQL introspection JSON response."""
    schema = introspection_data.get("data", {}).get("__schema", {})
    if not schema:
        return {"queries": [], "mutations": []}

    query_type_name = (schema.get("queryType") or {}).get("name", "Query")
    mutation_type_name = (schema.get("mutationType") or {}).get("name", "Mutation")

    queries: list[str] = []
    mutations: list[str] = []

    for t in schema.get("types", []):
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        fields = t.get("fields") or []
        field_names = [f.get("name") for f in fields if isinstance(f, dict) and f.get("name")]

        if name == query_type_name:
            queries.extend(field_names)
        elif name == mutation_type_name:
            mutations.extend(field_names)

    return {"queries": queries, "mutations": mutations}
