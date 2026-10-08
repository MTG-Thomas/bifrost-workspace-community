"""Verify ticket field updates cannot change their authorized target."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class TicketUpdateFieldTests(unittest.TestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            user_id="requester", org_id="org-a", email="requester@example.invalid",
            organization=SimpleNamespace(is_provider=False),
            is_platform_admin=False, is_function_key=False,
        )
        self.ticket = {"id": 101, "user_emailaddress": self.context.email}
        self.writes = []

        async def get_tickets(identity):
            return self.ticket

        async def create_tickets(payload):
            self.writes.append(payload)
            return payload

        sdk = types.ModuleType("bifrost")
        sdk.context = self.context
        sdk.UserError = UserError
        sdk.tool = lambda *args, **kwargs: lambda function: function
        halo = types.ModuleType("modules.halopsa")
        halo.get_tickets = get_tickets
        halo.create_tickets = create_tickets
        extension = types.ModuleType("modules.extensions.halopsa")
        for name in (
            "clean_html", "close_ticket_impl", "create_ticket", "get_enriched_ticket",
            "resolve_client_id",
        ):
            setattr(extension, name, lambda *args, **kwargs: None)
        self.patched = patch.dict(sys.modules, {
            "bifrost": sdk, "modules.halopsa": halo,
            "modules.extensions.halopsa": extension,
        })
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.names = ("shared.halopsa.tools._auth", "shared.halopsa.tools.tickets")
        self.clear_imported()
        self.addCleanup(self.clear_imported)
        self.update = importlib.import_module("shared.halopsa.tools.tickets").update_ticket

    def clear_imported(self):
        for name in self.names:
            sys.modules.pop(name, None)

    def test_rejects_target_swap_and_privileged_fields_for_org_user(self):
        for fields in ({"id": 202}, {"team_id": 7}, {"priority_id": 1}):
            with self.assertRaises(UserError):
                asyncio.run(self.update(101, fields))
        self.assertEqual(self.writes, [])
        asyncio.run(self.update(101, {"summary": "New summary", "category_2": 18}))
        self.assertEqual(self.writes, [[{
            "id": 101, "summary": "New summary", "categoryid_2": 18,
        }]])

    def test_admin_can_assign_but_cannot_swap_target(self):
        self.context.is_platform_admin = True
        asyncio.run(self.update(101, {"team_id": 7}))
        self.assertEqual(self.writes, [[{"id": 101, "team_id": 7}]])
        with self.assertRaises(UserError):
            asyncio.run(self.update(101, {"id": 202}))
        self.assertEqual(len(self.writes), 1)

    def test_mismatched_fetched_record_fails_before_write(self):
        self.ticket["id"] = 202
        with self.assertRaises(UserError):
            asyncio.run(self.update(101, {"summary": "New summary"}))
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
