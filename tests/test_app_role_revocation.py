"""Prove deselection revokes only grants recorded by this workflow."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class Response:
    def __init__(self, status, data=None):
        self.status_code = status
        self.data = data or {}
        self.text = ""

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class AppRoleRevocationTests(unittest.TestCase):
    def setUp(self):
        self.rows = {}
        self.graph_grants = {}
        self.graph_writes = []

        class Tables:
            async def query(inner, table, scope=None, limit=None):
                return SimpleNamespace(documents=[
                    SimpleNamespace(id=identity, data=data)
                    for (name, identity), data in self.rows.items() if name == table
                ])

            async def get(inner, table, identity, scope=None):
                data = self.rows.get((table, identity))
                return SimpleNamespace(id=identity, data=data) if data else None

            async def upsert(inner, table, id, data, scope=None):
                self.rows[(table, id)] = data

            async def delete(inner, table, identity, scope=None):
                self.rows.pop((table, identity), None)

        class Client:
            async def __aenter__(inner):
                return inner

            async def __aexit__(inner, *args):
                pass

            async def get(inner, url, **kwargs):
                if "appRoleAssignments" in url:
                    return Response(200, {"value": list(self.graph_grants.values())})
                if "appId='bifrost-app'" in url:
                    return Response(200, {"id": "app-sp"})
                return Response(200, {"id": "resource-sp", "appRoles": [{
                    "value": "Role.Read.All", "id": "role-id",
                }]})

            async def post(inner, url, **kwargs):
                self.graph_writes.append("grant")
                grant = {"id": "assignment-id", "appRoleId": "role-id", "resourceId": "resource-sp"}
                self.graph_grants[grant["id"]] = grant
                return Response(201, grant)

            async def delete(inner, url, **kwargs):
                self.graph_writes.append("revoke")
                self.graph_grants.pop(url.rsplit("/", 1)[-1], None)
                return Response(204)

        sdk = types.ModuleType("bifrost")
        sdk.context = SimpleNamespace(
            user_id="admin", org_id="provider", is_platform_admin=True, is_function_key=False
        )
        sdk.UserError = UserError
        sdk.workflow = lambda *args, **kwargs: lambda function: function
        sdk.tables = Tables()
        auth = types.ModuleType("modules.microsoft.auth")

        async def app_credentials():
            return SimpleNamespace(client_id="bifrost-app")

        async def graph_token(tenant_id):
            return "synthetic-token"

        auth.get_microsoft_app_credentials = app_credentials
        auth.get_graph_token = graph_token
        httpx = types.ModuleType("httpx")
        httpx.AsyncClient = Client
        self.patched = patch.dict(sys.modules, {
            "bifrost": sdk, "modules.microsoft.auth": auth, "httpx": httpx,
        })
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.names = (
            "modules.extensions.platform_auth",
            "features.microsoft_csp.workflows.save_permissions",
            "features.microsoft_csp.workflows.apply_partner_permissions",
        )
        self.clear_imported()
        self.addCleanup(self.clear_imported)
        self.save = importlib.import_module(
            "features.microsoft_csp.workflows.save_permissions"
        ).save_selected_permissions
        self.apply = importlib.import_module(
            "features.microsoft_csp.workflows.apply_partner_permissions"
        ).apply_partner_permissions
        self.permission = {
            "api_id": "resource-api", "api_name": "Resource API",
            "permission_name": "Role.Read.All", "permission_type": "application",
        }
        self.key = "resource-api:Role.Read.All:application"

    def clear_imported(self):
        for name in self.names:
            sys.modules.pop(name, None)

    def test_granted_role_is_revoked_after_deselection(self):
        asyncio.run(self.save([self.permission]))
        granted = asyncio.run(self.apply())
        self.assertEqual(granted["granted_count"], 1)
        self.assertEqual(self.graph_writes, ["grant"])
        asyncio.run(self.save([]))
        self.assertTrue(self.rows[("microsoft_pending_app_role_revocations", self.key)]["pending"])
        revoked = asyncio.run(self.apply())
        self.assertTrue(revoked["success"])
        self.assertEqual(revoked["revoked_count"], 1)
        self.assertEqual(self.graph_writes, ["grant", "revoke"])
        self.assertNotIn(("microsoft_pending_app_role_revocations", self.key), self.rows)

    def test_untracked_existing_grant_requires_manual_review(self):
        asyncio.run(self.save([self.permission]))
        self.graph_grants["manual-id"] = {
            "id": "manual-id", "appRoleId": "role-id", "resourceId": "resource-sp",
        }
        already = asyncio.run(self.apply())
        self.assertEqual(already["granted"][0]["status"], "already_granted")
        asyncio.run(self.save([]))
        result = asyncio.run(self.apply())
        self.assertFalse(result["success"])
        self.assertEqual(result["revoked_count"], 0)
        self.assertEqual(self.graph_writes, [])


if __name__ == "__main__":
    unittest.main()
