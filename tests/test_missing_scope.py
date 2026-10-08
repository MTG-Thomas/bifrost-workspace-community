"""Missing execution context must never become provider authorization."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class MissingScopeTests(unittest.TestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            user_id=None, org_id=None, email="caller@example.invalid",
            organization=None, is_platform_admin=False, is_function_key=False,
        )

        async def get_user(uid):
            return SimpleNamespace(is_superuser=False)

        sdk = types.ModuleType("bifrost")
        sdk.context = self.context
        sdk.UserError = UserError
        sdk.users = SimpleNamespace(get=get_user)
        sdk.roles = SimpleNamespace()
        self.patched = patch.dict(sys.modules, {"bifrost": sdk})
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.names = ("modules.extensions.permissions", "shared.halopsa.tools._auth")
        self.clear_imported()
        self.addCleanup(self.clear_imported)
        self.permissions = importlib.import_module("modules.extensions.permissions")
        self.halo_auth = importlib.import_module("shared.halopsa.tools._auth")

    def clear_imported(self):
        for name in self.names:
            sys.modules.pop(name, None)

    def test_missing_identity_or_org_cannot_bypass_role_and_ticket_checks(self):
        self.assertFalse(asyncio.run(self.permissions.is_provider()))
        self.assertFalse(asyncio.run(self.permissions.is_provider("someone-else")))
        with self.assertRaises(UserError):
            self.halo_auth.get_caller_scope()
        self.context.user_id = "caller"
        self.assertFalse(asyncio.run(self.permissions.is_provider()))
        self.assertFalse(asyncio.run(self.permissions.is_provider("someone-else")))
        with self.assertRaises(UserError):
            self.halo_auth.get_caller_scope()
        with self.assertRaises(UserError):
            asyncio.run(self.halo_auth.check_ticket_access({
                "user_emailaddress": self.context.email,
            }))

    def test_verified_admin_and_provider_org_are_allowed(self):
        self.context.user_id = "admin"
        self.context.is_platform_admin = True
        self.assertTrue(asyncio.run(self.permissions.is_provider()))
        self.assertTrue(self.halo_auth.get_caller_scope()["is_provider"])
        self.context.is_platform_admin = False
        self.context.org_id = "provider"
        self.context.organization = SimpleNamespace(is_provider=True)
        self.assertTrue(self.halo_auth.get_caller_scope()["is_provider"])
        self.context.is_function_key = True
        self.assertFalse(asyncio.run(self.permissions.is_provider()))
        with self.assertRaises(UserError):
            self.halo_auth.get_caller_scope()


if __name__ == "__main__":
    unittest.main()
