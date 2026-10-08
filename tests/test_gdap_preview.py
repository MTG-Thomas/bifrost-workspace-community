"""Verify GDAP previews bind destructive writes to reviewed snapshots."""

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class GdapPreviewTests(unittest.TestCase):
    def setUp(self):
        self.writes = []
        self.assignments = [{
            "id": "old-assignment", "status": "active",
            "accessContainer": {"accessContainerId": "old-group"},
            "accessDetails": {"unifiedRoles": [{"roleDefinitionId": "old-role"}]},
        }]
        self.template = [SimpleNamespace(id="new-group", data={
            "security_group_id": "new-group", "enabled": True,
            "unified_roles": [{"roleDefinitionId": "new-role"}],
        })]

        class Graph:
            def __init__(inner, token):
                pass

            def paginate(inner, path, params=None):
                if path.endswith("/accessAssignments"):
                    return list(self.assignments)
                return [{"id": "relationship-a", "status": "active"}]

            def get(inner, path, params=None):
                if path.startswith("/groups/"):
                    return {"displayName": "Group"}
                return {"id": "relationship-a", "status": "active"}

            def post(inner, path, body, headers=None):
                self.writes.append(("post", path))

            def patch(inner, path, body, headers=None):
                self.writes.append(("patch", path))

            def delete(inner, path, headers=None):
                self.writes.append(("delete", path))

        class Tables:
            async def query(inner, table, scope=None, limit=None):
                return SimpleNamespace(documents=list(self.template))

            async def delete(inner, table, id, scope=None):
                self.writes.append(("table-delete", id))

            async def upsert(inner, table, id, data, scope=None):
                self.writes.append(("table-upsert", id))

        sdk = types.ModuleType("bifrost")
        sdk.UserError = UserError
        sdk.context = SimpleNamespace(
            user_id="admin", org_id="provider", is_platform_admin=True, is_function_key=False
        )
        sdk.workflow = lambda *args, **kwargs: lambda function: function
        sdk.tables = Tables()
        async def list_mappings(_):
            return [SimpleNamespace(entity_id="tenant-a", entity_name="Tenant A")]

        sdk.integrations = SimpleNamespace(list_mappings=list_mappings)
        graph_module = types.ModuleType("modules.microsoft.graph")
        graph_module.GraphClient = Graph
        microsoft_package = types.ModuleType("modules.microsoft")
        microsoft_package.__path__ = [str(Path(__file__).resolve().parents[1] / "modules/microsoft")]
        auth_module = types.ModuleType("modules.microsoft.auth")

        async def token(_):
            return "synthetic-token"

        auth_module.get_graph_token = token
        self.patched = patch.dict(sys.modules, {
            "bifrost": sdk,
            "modules.microsoft": microsoft_package,
            "modules.microsoft.graph": graph_module,
            "modules.microsoft.auth": auth_module,
        })
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.names = (
            "modules.microsoft.gdap", "modules.extensions.platform_auth",
            "features.microsoft_csp.workflows.update_gdap_assignments",
            "features.microsoft_csp.workflows.seed_gdap_template",
            "features.microsoft_csp.workflows.batch_update_gdap",
        )
        self.clear_imported()
        self.addCleanup(self.clear_imported)
        self.update = importlib.import_module(
            "features.microsoft_csp.workflows.update_gdap_assignments"
        ).update_gdap_assignments
        self.seed = importlib.import_module(
            "features.microsoft_csp.workflows.seed_gdap_template"
        ).seed_gdap_template
        self.batch = importlib.import_module(
            "features.microsoft_csp.workflows.batch_update_gdap"
        ).batch_update_gdap

    def clear_imported(self):
        for name in self.names:
            sys.modules.pop(name, None)

    def test_assignment_preview_requires_matching_snapshot(self):
        preview = asyncio.run(self.update("tenant-a"))
        self.assertTrue(preview["preview"])
        self.assertEqual(preview["removed_groups"], ["old-group"])
        self.assertEqual(self.writes, [])
        with self.assertRaises(UserError):
            asyncio.run(self.update("tenant-a", confirmation_digest="wrong"))
        self.assertEqual(self.writes, [])
        applied = asyncio.run(self.update("tenant-a", confirmation_digest=preview["confirmation_digest"]))
        self.assertTrue(applied["success"])
        self.assertEqual([method for method, _ in self.writes], ["post", "delete"])

    def test_assignment_change_after_preview_blocks_mutation(self):
        preview = asyncio.run(self.update("tenant-a"))
        self.assignments[0]["id"] = "changed-assignment"
        with self.assertRaises(UserError):
            asyncio.run(self.update("tenant-a", confirmation_digest=preview["confirmation_digest"]))
        self.assertEqual(self.writes, [])

    def test_template_seed_previews_before_table_replacement(self):
        preview = asyncio.run(self.seed(relationship_id="relationship-a"))
        self.assertEqual(preview["current_groups"], ["new-group"])
        self.assertEqual(self.writes, [])
        with self.assertRaises(UserError):
            asyncio.run(self.seed(relationship_id="relationship-a", confirmation_digest="wrong"))
        self.assertEqual(self.writes, [])
        applied = asyncio.run(self.seed(
            relationship_id="relationship-a", confirmation_digest=preview["confirmation_digest"]
        ))
        self.assertEqual(applied["seeded_groups"], 1)
        self.assertEqual([method for method, _ in self.writes], ["table-delete", "table-upsert"])

    def test_batch_requires_each_tenants_reviewed_digest(self):
        preview = asyncio.run(self.batch())
        self.assertTrue(preview["preview"])
        self.assertEqual(self.writes, [])
        with self.assertRaises(UserError):
            asyncio.run(self.batch(confirmations={}))
        self.assertEqual(self.writes, [])
        digest = preview["previews"][0]["confirmation_digest"]
        applied = asyncio.run(self.batch(confirmations={"tenant-a": digest}))
        self.assertEqual(applied["synced"], 1)
        self.assertEqual([method for method, _ in self.writes], ["post", "delete"])


if __name__ == "__main__":
    unittest.main()
