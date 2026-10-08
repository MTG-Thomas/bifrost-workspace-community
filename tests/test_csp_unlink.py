"""Exercise CSP unlink cleanup against synthetic Bifrost SDK state."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class CspUnlinkTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.status = {}
        self.configs = {}
        self.mappings = {}

        class Tables:
            async def get(inner, table, identity, scope=None):
                data = self.status.get((scope, identity))
                return SimpleNamespace(data=data) if data is not None else None

            async def upsert(inner, table, id, data, scope=None):
                self.calls.append(("status", scope, id))
                self.status[(scope, id)] = data

        class Config:
            async def get(inner, key, scope=None):
                return self.configs.get((scope, key))

            async def set(inner, key, value, scope=None):
                self.calls.append(("config-set", scope, value))
                self.configs[(scope, key)] = value

            async def delete(inner, key, scope=None):
                self.calls.append(("config-delete", scope))
                return self.configs.pop((scope, key), None) is not None

        class Integrations:
            async def get_mapping(inner, name, scope=None):
                entity = self.mappings.get(scope)
                return SimpleNamespace(entity_id=entity) if entity else None

            async def upsert_mapping(inner, name, scope=None, entity_id=None, entity_name=None):
                self.calls.append(("mapping-upsert", scope, entity_id))
                self.mappings[scope] = entity_id

            async def delete_mapping(inner, name, scope=None):
                self.calls.append(("mapping-delete", scope))
                return self.mappings.pop(scope, None) is not None

        sdk = types.ModuleType("bifrost")
        sdk.context = SimpleNamespace(
            user_id="admin", org_id="provider", is_platform_admin=True, is_function_key=False
        )
        sdk.UserError = UserError
        sdk.workflow = lambda *args, **kwargs: lambda function: function
        sdk.tables = Tables()
        sdk.config = Config()
        sdk.integrations = Integrations()
        self.patched = patch.dict(sys.modules, {"bifrost": sdk})
        self.patched.start()
        self.addCleanup(self.patched.stop)
        for name in ("features.microsoft_csp.workflows.link_tenant", "modules.extensions.platform_auth"):
            sys.modules.pop(name, None)
        self.addCleanup(self.clear_imported)
        self.link = importlib.import_module(
            "features.microsoft_csp.workflows.link_tenant"
        ).link_csp_tenant

    @staticmethod
    def clear_imported():
        for name in ("features.microsoft_csp.workflows.link_tenant", "modules.extensions.platform_auth"):
            sys.modules.pop(name, None)

    def run_link(self, org_id):
        return asyncio.run(self.link("tenant-a", "Tenant A", "example.invalid", "customer-a", org_id, org_id))

    def test_unlink_removes_own_mapping_and_config_before_status(self):
        self.run_link("org-a")
        self.calls.clear()
        self.run_link(None)
        self.assertNotIn("org-a", self.mappings)
        self.assertNotIn(("org-a", "entra_tenant_id"), self.configs)
        self.assertEqual(self.status[("provider", "tenant-a")]["bifrost_org_id"], None)
        self.assertEqual(self.calls, [
            ("mapping-delete", "org-a"), ("config-delete", "org-a"),
            ("status", "provider", "tenant-a"),
        ])

    def test_unlink_preserves_a_replaced_org_mapping(self):
        self.run_link("org-a")
        self.mappings["org-a"] = "tenant-b"
        self.configs[("org-a", "entra_tenant_id")] = "tenant-b"
        self.calls.clear()
        self.run_link(None)
        self.assertEqual(self.mappings["org-a"], "tenant-b")
        self.assertEqual(self.configs[("org-a", "entra_tenant_id")], "tenant-b")
        self.assertEqual(self.calls, [("status", "provider", "tenant-a")])

    def test_relink_cleans_old_org_and_refuses_another_tenants_target(self):
        self.run_link("org-a")
        self.mappings["org-b"] = "tenant-b"
        self.calls.clear()
        with self.assertRaises(UserError):
            self.run_link("org-b")
        self.assertEqual(self.calls, [])
        self.mappings.pop("org-b")
        self.run_link("org-b")
        self.assertNotIn("org-a", self.mappings)
        self.assertNotIn(("org-a", "entra_tenant_id"), self.configs)
        self.assertEqual(self.mappings["org-b"], "tenant-a")


if __name__ == "__main__":
    unittest.main()
