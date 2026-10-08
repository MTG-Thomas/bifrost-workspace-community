"""Optional Microsoft grants require an operator-owned allowlist."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class PermissionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy_value = "[]"

        async def get(key, default=None, scope=None):
            return self.policy_value

        sdk = types.ModuleType("bifrost")
        sdk.UserError = UserError
        sdk.config = SimpleNamespace(get=get)
        self.patched = patch.dict(sys.modules, {"bifrost": sdk})
        self.patched.start()
        self.addCleanup(self.patched.stop)
        sys.modules.pop("modules.extensions.microsoft_permission_policy", None)
        self.addCleanup(lambda: sys.modules.pop("modules.extensions.microsoft_permission_policy", None))
        self.policy = importlib.import_module("modules.extensions.microsoft_permission_policy")
        self.optional = {
            "api_id": "00000003-0000-0000-c000-000000000000",
            "permission_name": "Role.Read.All", "permission_type": "application",
        }

    def check(self, permissions):
        return asyncio.run(self.policy.require_allowed_permissions(permissions, "provider"))

    def test_default_rejects_optional_application_role(self):
        with self.assertRaises(UserError):
            self.check([self.optional])
        self.check([{
            "api_id": self.optional["api_id"],
            "permission_name": "Directory.ReadWrite.All", "permission_type": "delegated",
        }])

    def test_exact_operator_entry_allows_role_but_not_arbitrary_api(self):
        self.policy_value = [self.optional]
        self.check([self.optional])
        forged = {**self.optional, "api_id": "attacker-api"}
        with self.assertRaises(UserError):
            self.check([forged])
        self.policy_value = [forged]
        with self.assertRaises(UserError):
            self.check([forged])

    def test_invalid_policy_fails_closed(self):
        self.policy_value = "not-json"
        with self.assertRaises(UserError):
            self.check([self.optional])


if __name__ == "__main__":
    unittest.main()
