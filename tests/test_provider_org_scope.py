"""Data providers must authorize an organization before changing scope."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class ProviderOrgScopeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        context = SimpleNamespace(user_id="ordinary", org_id="org-a", is_platform_admin=False,
                                  is_function_key=False)
        context.set_scope = lambda org: self.calls.append(("scope", org))
        self.context = context
        sdk = types.ModuleType("bifrost")
        sdk.context = context
        sdk.UserError = UserError
        sdk.data_provider = lambda *args, **kwargs: lambda function: function
        halo = types.ModuleType("modules.halopsa")

        async def list_sites(**kwargs):
            self.calls.append(("sites", kwargs))
            return SimpleNamespace(sites=[])

        async def list_tickets(**kwargs):
            self.calls.append(("tickets", kwargs))
            return {"tickets": []}

        halo.list_sites = list_sites
        halo.list_tickets = list_tickets
        extension = types.ModuleType("modules.extensions.halopsa")

        async def resolve_client_id(org):
            self.calls.append(("resolve", org))
            return 101

        async def list_projects(**kwargs):
            self.calls.append(("projects", kwargs))
            return []

        extension.resolve_client_id = resolve_client_id
        extension.list_projects = list_projects
        exchange = types.ModuleType("modules.microsoft.exchange")

        async def create_exchange_client(**kwargs):
            self.calls.append(("exchange", kwargs))
            return SimpleNamespace(get_mailboxes=lambda **kw: [])

        exchange.create_exchange_client = create_exchange_client
        self.patched = patch.dict(sys.modules, {
            "bifrost": sdk,
            "modules.halopsa": halo,
            "modules.extensions.halopsa": extension,
            "modules.microsoft.exchange": exchange,
        })
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.modules = (
            "modules.extensions.platform_auth",
            "shared.halopsa.data_providers",
            "shared.microsoft.exchange_data_providers",
        )
        for name in self.modules:
            sys.modules.pop(name, None)
        self.addCleanup(lambda: [sys.modules.pop(name, None) for name in self.modules])

    def providers(self):
        halo = importlib.import_module("shared.halopsa.data_providers")
        exchange = importlib.import_module("shared.microsoft.exchange_data_providers")
        return (
            halo.halo_client_sites,
            halo.halo_client_projects,
            halo.halo_open_tickets,
            exchange.list_shared_mailboxes,
        )

    def test_foreign_anonymous_and_function_key_rejected_before_scope_or_vendor(self):
        for provider in self.providers():
            for user_id, function_key in (("ordinary", False), (None, False), ("ordinary", True)):
                self.context.user_id = user_id
                self.context.is_function_key = function_key
                with self.subTest(provider=provider.__name__, user_id=user_id, function_key=function_key):
                    with self.assertRaises(UserError):
                        asyncio.run(provider(org_id="org-b"))
                    self.assertEqual(self.calls, [])

    def test_owned_scope_and_verified_admin_access(self):
        for provider in self.providers():
            self.calls.clear()
            self.context.user_id = "ordinary"
            self.context.is_function_key = False
            asyncio.run(provider(org_id="org-a"))
            self.assertIn(("scope", "org-a"), self.calls)
            self.calls.clear()
            self.context.user_id = "admin"
            self.context.is_platform_admin = True
            asyncio.run(provider(org_id="org-b"))
            self.assertIn(("scope", "org-b"), self.calls)


if __name__ == "__main__":
    unittest.main()
