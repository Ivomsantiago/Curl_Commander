"""Tests for the OpenAPI + Postman collection importers (item 4)."""

import json
import types

import pytest

from curlcommander.cli import runner
from curlcommander.core.importers import SpecImportError, parse_openapi, parse_postman
from curlcommander.core.importers.postman import load_env
from curlcommander.storage.history_repo import HistoryRepo

# --- OpenAPI --------------------------------------------------------------

_OPENAPI = {
    "openapi": "3.0.3",
    "servers": [{"url": "https://api.example.com/v1"}],
    "components": {
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
        "schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                    "role": {"type": "string", "enum": ["admin", "user"]},
                },
            }
        },
    },
    "security": [{"bearer": []}],
    "paths": {
        "/users/{id}": {
            "get": {
                "parameters": [
                    {"name": "id", "in": "path", "schema": {"type": "integer"}},
                    {"name": "verbose", "in": "query", "schema": {"type": "boolean", "default": True}},
                ]
            }
        },
        "/users": {
            "post": {
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}}
            }
        },
    },
}


def test_openapi_basic_shape_and_auth():
    configs = parse_openapi(_OPENAPI)
    by_key = {(c.method, c.url): c for c in configs}
    assert len(configs) == 2

    get = by_key[("GET", "https://api.example.com/v1/users/{id}".replace("{id}", "FUZZ"))]
    # path param has no example -> FUZZ marker substituted into the path
    assert get.url == "https://api.example.com/v1/users/FUZZ"
    assert get.params.get("verbose") == "True"  # default honoured
    assert get.auth_type == "bearer"
    assert get.auth_value == "FUZZ"


def test_openapi_request_body_from_ref_with_fuzz_and_enum():
    configs = parse_openapi(_OPENAPI)
    post = next(c for c in configs if c.method == "POST")
    assert post.body_type == "json"
    body = json.loads(post.body)
    assert body["name"] == "FUZZ"  # untyped string -> fuzzable
    assert body["age"] == 0  # integer default
    assert body["role"] == "admin"  # first enum value


def test_openapi_malformed_raises():
    with pytest.raises(SpecImportError):
        parse_openapi({"openapi": "3.0.0"})  # no paths
    with pytest.raises(SpecImportError):
        parse_openapi({"paths": {}})  # no openapi key


def test_openapi_recursive_schema_terminates():
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/n": {
                "post": {
                    "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}
                }
            }
        },
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}, "label": {"type": "string"}},
                }
            }
        },
    }
    post = parse_openapi(spec)[0]
    body = json.loads(post.body)
    assert body["label"] == "FUZZ"
    assert body["child"] == {}  # recursion broken, not infinite


# --- Postman --------------------------------------------------------------

_POSTMAN = {
    "info": {"name": "demo", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "item": [
        {
            "name": "folder",
            "item": [
                {
                    "name": "get user",
                    "request": {
                        "method": "GET",
                        "header": [{"key": "Accept", "value": "application/json"}],
                        "url": {"raw": "{{base}}/users/{{uid}}?verbose=1", "query": [{"key": "verbose", "value": "1"}]},
                        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{tok}}"}]},
                    },
                }
            ],
        },
        {
            "name": "create",
            "request": {
                "method": "POST",
                "body": {"mode": "urlencoded", "urlencoded": [{"key": "name", "value": "{{who}}"}]},
                "url": "{{base}}/users",
            },
        },
    ],
}


def test_postman_var_resolution_and_nesting():
    env = {"base": "https://api.test", "uid": "42", "tok": "SECRET"}
    configs = parse_postman(_POSTMAN, env)
    assert len(configs) == 2  # nested folder + top-level request both found

    get = configs[0]
    assert get.url == "https://api.test/users/42"
    assert get.params.get("verbose") == "1"
    assert get.auth_type == "bearer"
    assert get.auth_value == "SECRET"

    post = configs[1]
    assert post.body_type == "form"
    assert post.body == "name={{who}}"  # unresolved var stays literal, not dropped


def test_postman_malformed_raises():
    with pytest.raises(SpecImportError):
        parse_postman({"item": []})  # no info
    with pytest.raises(SpecImportError):
        parse_postman({"info": {"name": "x"}})  # no item


def test_load_env_from_export(tmp_path):
    export = {
        "values": [
            {"key": "base", "value": "https://x", "enabled": True},
            {"key": "off", "value": "nope", "enabled": False},
        ]
    }
    p = tmp_path / "env.json"
    p.write_text(json.dumps(export), encoding="utf-8")
    env = load_env(str(p))
    assert env == {"base": "https://x"}


# --- CLI runner dispatch --------------------------------------------------


def test_run_import_persists_to_history(tmp_path, capsys):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_OPENAPI), encoding="utf-8")
    out_path = tmp_path / "collection.json"
    db_path = tmp_path / "h.db"

    args = types.SimpleNamespace(format="openapi", spec=str(spec_path), out=str(out_path), env=None, postman_env=None)
    repo = HistoryRepo(db_path)
    try:
        code = runner._run_import(args, repo)
        entries = repo.load()
    finally:
        repo.close()

    assert code == runner.EXIT_OK
    assert len(entries) == 2
    assert all(e.origin == "openapi:spec.json" for e in entries)
    assert out_path.exists()
    assert "Importadas 2" in capsys.readouterr().out
