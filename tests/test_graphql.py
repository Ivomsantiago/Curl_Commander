"""Tests for GraphQL request builder and schema introspection parser."""

import json
from curlcommander.core.graphql import INTROSPECTION_QUERY, build_graphql_request, extract_operations


def test_build_graphql_request():
    req = build_graphql_request(
        url="https://api.example.com/graphql",
        query="query { user { id name } }",
        variables={"id": 1},
    )
    assert req.method == "POST"
    assert req.url == "https://api.example.com/graphql"
    assert req.headers["Content-Type"] == "application/json"
    body = json.loads(req.body)
    assert body["query"] == "query { user { id name } }"
    assert body["variables"] == {"id": 1}


def test_extract_operations():
    mock_introspection = {
        "data": {
            "__schema": {
                "queryType": {"name": "Query"},
                "mutationType": {"name": "Mutation"},
                "types": [
                    {
                        "name": "Query",
                        "fields": [{"name": "getUser"}, {"name": "listItems"}],
                    },
                    {
                        "name": "Mutation",
                        "fields": [{"name": "createUser"}],
                    },
                ],
            }
        }
    }
    ops = extract_operations(mock_introspection)
    assert ops["queries"] == ["getUser", "listItems"]
    assert ops["mutations"] == ["createUser"]
