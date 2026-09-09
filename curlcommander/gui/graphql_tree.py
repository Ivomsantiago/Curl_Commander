"""GraphQL introspection visual explorer."""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Tree


class GraphQLTreePanel(VerticalScroll):
    DEFAULT_CSS = """
    GraphQLTreePanel { height: 15; border: round $accent; display: none; margin-top: 1; }
    GraphQLTreePanel.-active { display: block; }
    """

    class QueryGenerated(Message):
        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    def compose(self) -> ComposeResult:
        tree: Tree[Any] = Tree("GraphQL Schema")
        tree.root.expand()
        yield tree

    def load_schema(self, introspection_json: str) -> None:
        try:
            data = json.loads(introspection_json)
            schema = data.get("data", {}).get("__schema", {})
        except Exception:
            return

        tree = self.query_one(Tree)
        tree.clear()

        types = schema.get("types", [])

        # We focus on the Query and Mutation types first
        query_type_name = schema.get("queryType", {}).get("name") if schema.get("queryType") else "Query"
        mutation_type_name = schema.get("mutationType", {}).get("name") if schema.get("mutationType") else "Mutation"

        query_node = tree.root.add("Queries", expand=True)
        mutation_node = tree.root.add("Mutations", expand=True)
        other_node = tree.root.add("Other Types", expand=False)

        for t in types:
            name = t.get("name", "")
            if name.startswith("__"):
                continue

            node = None
            if name == query_type_name:
                node = query_node
            elif name == mutation_type_name:
                node = mutation_node
            else:
                # Add to other types if it's an object type
                if t.get("kind") == "OBJECT":
                    node = other_node

            if node is not None:
                type_node = node.add(name, expand=True)
                for field in t.get("fields", []) or []:
                    # store field data in the node
                    field_name = field.get("name", "")
                    field_node = type_node.add(f"{field_name}", data={"type": name, "field": field})
                    # We can add args as children
                    for arg in field.get("args", []) or []:
                        field_node.add(f"arg: {arg.get('name')}")

        self.add_class("-active")

    def _generate_query(self, data: dict[str, Any]) -> str:
        field = data["field"]
        parent_type = data["type"]

        is_mutation = "Mutation" in parent_type  # rough heuristic
        op = "mutation" if is_mutation else "query"

        # Generate a basic query
        field_name = field.get("name", "")
        args = field.get("args", []) or []

        arg_str = ""
        if args:
            arg_str = "(" + ", ".join([f"{a['name']}: \"\"" for a in args]) + ")"

        query = f"{op} {{\n  {field_name}{arg_str} {{\n    # add fields here\n  }}\n}}"
        return json.dumps({"query": query}, indent=2)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return

        payload = self._generate_query(data)
        self.post_message(self.QueryGenerated(payload))
