import json

import pytest
from textual.app import App

from curlcommander.gui.graphql_tree import GraphQLTreePanel


@pytest.mark.asyncio
async def test_graphql_tree_panel():
    class DummyApp(App):
        def __init__(self):
            super().__init__()
            self.caught = None

        def compose(self):
            yield GraphQLTreePanel()

        def on_graphql_tree_panel_query_generated(self, event):
            self.caught = event

    app = DummyApp()
    async with app.run_test() as pilot:
        panel = app.query_one(GraphQLTreePanel)

        # Initial state
        assert "GraphQL Schema" in str(panel.query_one("Tree").root.label)

        # Mock introspection data
        mock_data = {
            "data": {
                "__schema": {
                    "queryType": {"name": "Query"},
                    "mutationType": {"name": "Mutation"},
                    "types": [
                        {"kind": "OBJECT", "name": "Query", "fields": [{"name": "getUser", "args": [{"name": "id"}]}]}
                    ],
                }
            }
        }

        panel.load_schema(json.dumps(mock_data))

        # Check if the tree populated
        tree = panel.query_one("Tree")
        queries_node = None
        for child in tree.root.children:
            if str(child.label) == "Queries":
                queries_node = child
                break

        assert queries_node is not None
        query_type_node = queries_node.children[0]
        assert str(query_type_node.label) == "Query"

        get_user_node = query_type_node.children[0]
        assert str(get_user_node.label) == "getUser"
        # Test the query generator
        data = get_user_node.data
        assert data is not None
        payload = panel._generate_query(data)
        assert "getUser" in payload
        assert "query" in payload
        assert "id:" in payload
