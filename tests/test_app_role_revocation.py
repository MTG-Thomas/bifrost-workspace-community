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
                assignment_id = url.rsplit("/", 1)[-1]
                existed = self.graph_grants.pop(assignment_id, None)
                return Response(204 if existed else 404)

        sdk = types.ModuleType("bifrost")
        sdk.context = SimpleNamespace(
            user_id="admin", org_id="provider", is_platform_admin=True, is_function_key=False
        )
        sdk.UserError = UserError
        sdk.workflow = lambda *args, **kwargs: lambda function: function
        sdk.tables = Tables()
        async def policy_get(key, default=None, scope=None):
            return [{
                "api_id": "00000003-0000-0000-c000-000000000000",
                "permission_name": "Role.Read.All",
                "permission_type": "application",
            }]

        sdk.config = SimpleNamespace(get=policy_get)
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
            "modules.extensions.microsoft_permission_policy",
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
            "api_id": "00000003-0000-0000-c000-000000000000", "api_name": "Microsoft Graph",
            "permission_name": "Role.Read.All", "permission_type": "application",
        }
        self.key = "00000003-0000-0000-c000-000000000000:Role.Read.All:application"

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

    def test_already_managed_existing_grant_remains_successful(self):
        asyncio.run(self.save([self.permission]))
        asyncio.run(self.apply())
        existing = asyncio.run(self.apply())
        self.assertTrue(existing["success"])
        self.assertEqual(existing["granted"][0]["status"], "already_granted")
        self.assertEqual(existing["adopted_count"], 0)
        self.assertEqual(self.graph_writes, ["grant"])

    def test_untracked_existing_grant_requires_explicit_adoption(self):
        asyncio.run(self.save([self.permission]))
        self.graph_grants["manual-id"] = {
            "id": "manual-id", "appRoleId": "role-id", "resourceId": "resource-sp",
        }
        already = asyncio.run(self.apply())
        self.assertFalse(already["success"])
        self.assertEqual(already["granted_count"], 0)
        self.assertIn("unmanaged", already["errors"][0]["error"])
        self.assertNotIn(("microsoft_managed_app_role_assignments", self.key), self.rows)

    def test_explicit_adoption_tracks_then_revokes_existing_grant(self):
        asyncio.run(self.save([self.permission]))
        self.graph_grants["manual-id"] = {
            "id": "manual-id", "appRoleId": "role-id", "resourceId": "resource-sp",
        }
        adopted = asyncio.run(self.apply(adopt_existing_assignments=True))
        self.assertTrue(adopted["success"])
        self.assertEqual(adopted["adopted_count"], 1)
        self.assertEqual(
            self.rows[("microsoft_managed_app_role_assignments", self.key)]["assignment_id"],
            "manual-id",
        )
        asyncio.run(self.save([]))
        result = asyncio.run(self.apply())
        self.assertTrue(result["success"])
        self.assertEqual(result["revoked_count"], 1)
        self.assertEqual(self.graph_writes, ["revoke"])

    def test_explicit_adoption_revokes_pending_preledger_grant(self):
        asyncio.run(self.save([self.permission]))
        self.graph_grants["legacy-id"] = {
            "id": "legacy-id", "appRoleId": "role-id", "resourceId": "resource-sp",
        }
        asyncio.run(self.save([]))
        result = asyncio.run(self.apply(adopt_existing_assignments=True))
        self.assertTrue(result["success"])
        self.assertEqual(result["adopted_count"], 1)
        self.assertEqual(result["revoked_count"], 1)
        self.assertEqual(result["adopted"][0]["status"], "adopted_for_revocation")
        self.assertEqual(self.graph_writes, ["revoke"])
        self.assertNotIn(("microsoft_pending_app_role_revocations", self.key), self.rows)

    def test_replaced_managed_grant_requires_readoption_before_revocation(self):
        asyncio.run(self.save([self.permission]))
        asyncio.run(self.apply())
        self.graph_grants = {
            "replacement-id": {
                "id": "replacement-id",
                "appRoleId": "role-id",
                "resourceId": "resource-sp",
            }
        }
        asyncio.run(self.save([]))
        refused = asyncio.run(self.apply())
        self.assertFalse(refused["success"])
        self.assertIn("changed", refused["errors"][0]["error"])
        self.assertIn("replacement-id", self.graph_grants)
        reconciled = asyncio.run(self.apply(adopt_existing_assignments=True))
        self.assertTrue(reconciled["success"])
        self.assertEqual(reconciled["adopted"][0]["status"], "adopted_replacement_for_revocation")
        self.assertNotIn("replacement-id", self.graph_grants)

    def test_rejects_non_boolean_adoption_flag(self):
        with self.assertRaisesRegex(UserError, "must be true or false"):
            asyncio.run(self.apply(adopt_existing_assignments="true"))


if __name__ == "__main__":
    unittest.main()
