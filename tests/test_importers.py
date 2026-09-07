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


def test_openapi_security_basic_and_apikey_and_form_body():
    spec = {
        "openapi": "3.0.0",
        "components": {
            "securitySchemes": {
                "basic": {"type": "http", "scheme": "basic"},
                "key": {"type": "apiKey", "in": "header", "name": "X-Key"},
            }
        },
        "paths": {
            "/basic": {"get": {"security": [{"basic": []}]}},
            "/key": {"get": {"security": [{"key": []}]}},
            "/form": {
                "post": {
                    "requestBody": {"content": {"application/x-www-form-urlencoded": {"schema": {"type": "object"}}}}
                }
            },
            "/ex": {
                "post": {
                    "requestBody": {"content": {"application/json": {"example": {"a": 1}}}},
                    "parameters": [{"name": "q", "in": "query", "example": "v"}],
                }
            },
        },
    }
    by = {c.url.rsplit("/", 1)[-1]: c for c in parse_openapi(spec)}
    assert by["basic"].auth_type == "basic" and by["basic"].auth_value == "FUZZ:FUZZ"
    assert by["key"].auth_type == "apikey" and by["key"].auth_value == "X-Key: FUZZ"
    assert by["form"].body_type == "form" and "FUZZ" in by["form"].body
    assert json.loads(by["ex"].body) == {"a": 1}  # requestBody example used verbatim
    assert by["ex"].params.get("q") == "v"  # parameter-level example


def test_openapi_scalar_schema_types_and_no_servers():
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "n": {"type": "number"},
                                        "b": {"type": "boolean"},
                                        "arr": {"type": "array", "items": {"type": "integer"}},
                                    },
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    cfg = parse_openapi(spec)[0]
    assert cfg.url == "https://HOST/x"  # no servers[] -> placeholder host
    body = json.loads(cfg.body)
    assert body == {"n": 0, "b": False, "arr": [0]}


def test_openapi_load_spec_yaml(tmp_path):
    from curlcommander.core.importers.openapi import load_spec

    p = tmp_path / "spec.yaml"
    p.write_text("openapi: 3.0.0\npaths:\n  /y:\n    get: {}\n", encoding="utf-8")
    spec = load_spec(str(p))
    assert parse_openapi(spec)[0].method == "GET"


def test_postman_auth_basic_apikey_and_string_url():
    env = {"u": "alice", "p": "s3cr3t", "kv": "K1"}
    coll = {
        "info": {"name": "c"},
        "item": [
            {
                "name": "basic",
                "request": {
                    "method": "GET",
                    "url": "https://x/basic",
                    "auth": {
                        "type": "basic",
                        "basic": [{"key": "username", "value": "{{u}}"}, {"key": "password", "value": "{{p}}"}],
                    },
                },
            },
            {
                "name": "apikey",
                "request": {
                    "method": "GET",
                    "url": "https://x/key",
                    "header": [{"key": "Off", "value": "x", "disabled": True}],
                    "auth": {
                        "type": "apikey",
                        "apikey": [{"key": "key", "value": "X-Api"}, {"key": "value", "value": "{{kv}}"}],
                    },
                },
            },
        ],
    }
    configs = parse_postman(coll, env)
    basic, apikey = configs
    assert basic.auth_type == "basic" and basic.auth_value == "alice:s3cr3t"
    assert basic.url == "https://x/basic"  # plain string url
    assert apikey.auth_type == "apikey" and apikey.auth_value == "X-Api: K1"
    assert apikey.headers.get("Off") is None  # disabled header skipped


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
