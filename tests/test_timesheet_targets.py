"""Exercise timesheet target checks with synthetic HaloPSA responses."""

import asyncio
import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class UserError(Exception):
    pass


class TimesheetTargetTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.context = SimpleNamespace(
            user_id="ordinary-user",
            org_id="org-a",
            email="agent@example.invalid",
            organization=SimpleNamespace(is_provider=False),
            is_platform_admin=False,
        )
        sdk = types.ModuleType("bifrost")
        sdk.context = self.context
        sdk.UserError = UserError
        sdk.tool = lambda *args, **kwargs: lambda function: function
        halo = types.ModuleType("modules.halopsa")
        self.appointment = {"id": 909, "agents": [{"id": 22}], "client_id": 100}
        self.action = {"id": 808, "who_agentid": 22, "ticket_id": 202}
        self.ticket = {"id": 202, "agent_id": 22, "user_email": "requester@example.invalid"}
        self.event = {"id": 707, "agent_id": 22, "event_type": 1}

        async def list_agents():
            return {"agents": [{"id": 11, "name": "Agent", "email": self.context.email}]}

        async def get_appointment(identity):
            self.calls.append(("get_appointment", identity))
            return self.appointment

        async def get_actions(identity):
            self.calls.append(("get_actions", identity))
            return self.action

        async def get_tickets(identity):
            self.calls.append(("get_tickets", identity))
            return self.ticket

        async def get_timesheet_event(identity):
            self.calls.append(("get_timesheet_event", identity))
            return self.event

        def mutation(name):
            async def call(payload):
                self.calls.append((name, payload))
                return {"id": payload} if name == "delete_timesheet_event" else payload
            return call

        halo.list_agents = list_agents
        halo.get_appointment = get_appointment
        halo.get_actions = get_actions
        halo.get_tickets = get_tickets
        halo.get_timesheet_event = get_timesheet_event
        for name in ("create_appointment", "create_actions", "create_timesheet_event", "delete_timesheet_event"):
            setattr(halo, name, mutation(name))
        extension = types.ModuleType("modules.extensions.halopsa")

        async def resolve_client_id(org_id):
            self.calls.append(("resolve_client_id", org_id))
            return 100

        extension.resolve_client_id = resolve_client_id
        self.patched = patch.dict(sys.modules, {
            "bifrost": sdk,
            "modules.halopsa": halo,
            "modules.extensions.halopsa": extension,
        })
        self.patched.start()
        self.addCleanup(self.patched.stop)
        for name in ("shared.halopsa.tools.fill_day", "shared.halopsa.tools.timeentry", "shared.halopsa.tools._auth"):
            sys.modules.pop(name, None)
        self.addCleanup(self.clear_imported)
        self.fill_day = importlib.import_module("shared.halopsa.tools.fill_day").fill_day
        self.timeentry = importlib.import_module("shared.halopsa.tools.timeentry")

    @staticmethod
    def clear_imported():
        for name in ("shared.halopsa.tools.fill_day", "shared.halopsa.tools.timeentry", "shared.halopsa.tools._auth"):
            sys.modules.pop(name, None)

    @staticmethod
    def block(action, **extra):
        return {
            "action": action,
            "start": "2026-10-07T12:00:00Z",
            "end": "2026-10-07T13:00:00Z",
            "note": "synthetic work",
            **extra,
        }

    def result(self, block):
        return asyncio.run(self.fill_day([block]))

    def mutations(self):
        return [name for name, _ in self.calls if name.startswith(("create_", "delete_"))]

    def test_foreign_appointment_and_missing_record_fail_before_mutation(self):
        foreign = self.result(self.block("complete", appointment_id=909, client_id=100))
        self.assertEqual((foreign["completed"], foreign["failed"]), (0, 1))
        self.assertEqual(self.mutations(), [])
        self.appointment = {}
        missing = self.result(self.block("complete", appointment_id=909))
        self.assertEqual((missing["completed"], missing["failed"]), (0, 1))
        self.assertEqual(self.mutations(), [])

    def test_owned_appointment_can_complete_but_not_for_a_different_client(self):
        self.appointment["agents"] = [{"id": 11}]
        wrong_client = self.result(self.block("complete", appointment_id=909, client_id=999))
        self.assertEqual(wrong_client["completed"], 0)
        self.assertEqual(self.mutations(), [])
        allowed = self.result(self.block("complete", appointment_id=909, client_id=100))
        self.assertEqual(allowed["completed"], 1)
        self.assertEqual(self.mutations(), ["create_appointment", "create_timesheet_event"])

    def test_action_requires_same_agent_and_ticket(self):
        foreign = self.result(self.block("adjust", action_id=808, ticket_id=202))
        self.assertEqual(foreign["completed"], 0)
        self.assertEqual(self.mutations(), [])
        self.action["who_agentid"] = 11
        swapped_ticket = self.result(self.block("adjust", action_id=808, ticket_id=303))
        self.assertEqual(swapped_ticket["completed"], 0)
        self.assertEqual(self.mutations(), [])
        allowed = self.result(self.block("adjust", action_id=808, ticket_id=202))
        self.assertEqual(allowed["completed"], 1)
        self.assertEqual(self.mutations(), ["create_actions"])

    def test_quicktime_client_is_org_scoped_unless_platform_admin(self):
        provider_default = self.result(self.block("log"))
        self.assertEqual(provider_default["completed"], 0)
        denied = self.result(self.block("log", client_id=999))
        self.assertEqual(denied["completed"], 0)
        self.assertEqual(self.mutations(), [])
        owned = self.result(self.block("log", client_id=100))
        self.assertEqual(owned["completed"], 1)
        self.context.is_platform_admin = True
        provider = self.result(self.block("log", client_id=999))
        self.assertEqual(provider["completed"], 1)
        self.assertEqual(self.mutations(), ["create_timesheet_event", "create_timesheet_event"])
        self.context.is_function_key = True
        keyed = self.result(self.block("log", client_id=999))
        self.assertEqual(keyed["completed"], 0)

    def test_direct_appointment_action_and_break_tools_bind_owner(self):
        with self.assertRaises(UserError):
            asyncio.run(self.timeentry.complete_appointment(909, 1))
        with self.assertRaises(UserError):
            asyncio.run(self.timeentry.adjust_time_entry(808, 202, 1))
        with self.assertRaises(UserError):
            asyncio.run(self.timeentry.delete_break_entry(707))
        self.assertEqual(self.mutations(), [])
        self.appointment["agents"] = [{"id": 11}]
        self.action["who_agentid"] = 11
        self.event["agent_id"] = 11
        asyncio.run(self.timeentry.complete_appointment(909, 1))
        asyncio.run(self.timeentry.adjust_time_entry(808, 202, 1))
        asyncio.run(self.timeentry.delete_break_entry(707))
        self.assertEqual(self.mutations(), ["create_appointment", "create_actions", "delete_timesheet_event"])

    def test_direct_quicktime_and_email_bind_client_ticket_and_recipient(self):
        with self.assertRaises(UserError):
            asyncio.run(self.timeentry.log_quicktime("start", "end", client_id=999))
        with self.assertRaises(UserError):
            asyncio.run(self.timeentry.send_ticket_email(202, "other@example.invalid", "hello"))
        self.assertEqual(self.mutations(), [])
        self.ticket["agent_id"] = 11
        with self.assertRaises(UserError):
            asyncio.run(self.timeentry.send_ticket_email(202, "other@example.invalid", "hello"))
        asyncio.run(self.timeentry.log_quicktime("start", "end", client_id=100))
        asyncio.run(self.timeentry.send_ticket_email(202, "requester@example.invalid", "hello"))
        self.assertEqual(self.mutations(), ["create_timesheet_event", "create_actions"])


if __name__ == "__main__":
    unittest.main()
