"""A ticket match key cannot reuse another client's ticket."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class TicketMatchScopeTests(unittest.TestCase):
    def setUp(self):
        self.records = {}
        self.tickets = {}
        self.lookups = []
        sdk = types.ModuleType("bifrost")

        async def get(table, key):
            self.lookups.append(key)
            record = self.records.get(key)
            return SimpleNamespace(data=record) if record else None

        async def upsert(table, key, data):
            self.records[key] = data

        async def config_get(key):
            return None

        sdk.tables = SimpleNamespace(get=get, upsert=upsert)
        sdk.config = SimpleNamespace(get=config_get)
        sdk.context = SimpleNamespace()
        sdk.executions = sdk.integrations = SimpleNamespace()
        sdk.UserError = ValueError
        halo = types.ModuleType("modules.halopsa")

        async def create_tickets(payload):
            client_id = payload[0]["client_id"]
            ticket = {"id": len(self.tickets) + 100, "client_id": client_id, "hasbeenclosed": False}
            self.tickets[ticket["id"]] = ticket
            return [ticket]

        async def get_tickets(identity):
            return self.tickets[int(identity)]

        halo.create_tickets = create_tickets
        halo.get_tickets = get_tickets
        self.patched = patch.dict(sys.modules, {"bifrost": sdk, "modules.halopsa": halo})
        self.patched.start()
        self.addCleanup(self.patched.stop)
        sys.modules.pop("modules.extensions.halopsa", None)
        self.addCleanup(lambda: sys.modules.pop("modules.extensions.halopsa", None))
        self.create_ticket = importlib.import_module("modules.extensions.halopsa").create_ticket

    def test_same_match_id_is_separate_for_each_client(self):
        first = asyncio.run(self.create_ticket("Synthetic", 1, match_id="same"))
        self.assertTrue(first["is_new"])
        self.assertEqual(self.lookups, ["1:same"])
        second = asyncio.run(self.create_ticket("Synthetic", 2, match_id="same"))
        self.assertTrue(second["is_new"])
        self.assertEqual(set(self.records), {"1:same", "2:same"})
        repeat = asyncio.run(self.create_ticket("Synthetic", 1, match_id="same"))
        self.assertFalse(repeat["is_new"])
        self.assertEqual(repeat["id"], first["id"])

    def test_poisoned_mapping_cannot_reuse_foreign_client_ticket(self):
        foreign = asyncio.run(self.create_ticket("Foreign", 2))
        self.records["1:same"] = {"ticket_id": foreign["id"], "client_id": 1}
        result = asyncio.run(self.create_ticket("Synthetic", 1, match_id="same"))
        self.assertTrue(result["is_new"])
        self.assertNotEqual(result["id"], foreign["id"])


if __name__ == "__main__":
    unittest.main()
