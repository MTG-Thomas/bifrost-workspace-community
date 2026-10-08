"""Provider-wide workflow entry points reject callers before vendor access."""

import asyncio
import ast
import importlib
import inspect
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CSP = ROOT / "features" / "microsoft_csp" / "workflows"


class UserError(Exception):
    pass


class PlatformAdminGateTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.context = SimpleNamespace(
            user_id="ordinary-user",
            is_platform_admin=False,
            is_function_key=False,
        )
        sdk = types.ModuleType("bifrost")
        sdk.context = self.context
        sdk.UserError = UserError
        sdk.workflow = sdk.tool = lambda *args, **kwargs: lambda function: function
        sdk.config = SimpleNamespace(get=lambda key, default=None: default)
        sdk.tables = sdk.integrations = sdk.organizations = SimpleNamespace()

        extension = types.ModuleType("modules.extensions.halopsa")

        async def execute_sql(query):
            self.calls.append(("report", query))
            return [{"customer": "synthetic"}]

        extension.execute_sql = execute_sql
        microsoft = types.ModuleType("modules.microsoft")
        microsoft.__path__ = [str(ROOT / "modules" / "microsoft")]
        microsoft.gdap = types.ModuleType("modules.microsoft.gdap")
        auth = types.ModuleType("modules.microsoft.auth")
        auth.get_graph_token = lambda *args, **kwargs: self.calls.append(("graph-token", args))
        graph = types.ModuleType("modules.microsoft.graph")
        graph.GraphClient = lambda *args: self.calls.append(("graph-client", args))
        httpx = types.ModuleType("httpx")
        httpx.AsyncClient = type("AsyncClient", (), {})
        self.patched = patch.dict(sys.modules, {
            "bifrost": sdk,
            "modules.extensions.halopsa": extension,
            "modules.microsoft": microsoft,
            "modules.microsoft.gdap": microsoft.gdap,
            "modules.microsoft.auth": auth,
            "modules.microsoft.graph": graph,
            "httpx": httpx,
        })
        self.patched.start()
        self.addCleanup(self.patched.stop)
        for name in list(sys.modules):
            if name.startswith("features.microsoft_csp.workflows.") or name in (
                "features.autoelevate.workflows.tools",
                "features.halopsa_reporting.workflows.execute_halopsa_sql",
                "features.tdsynnex_partner.workflows.tools",
                "modules.extensions.platform_auth",
            ):
                sys.modules.pop(name, None)
        self.addCleanup(self.clear_imported)

    @staticmethod
    def clear_imported():
        for name in list(sys.modules):
            if name.startswith("features.microsoft_csp.workflows.") or name in (
                "features.autoelevate.workflows.tools",
                "features.halopsa_reporting.workflows.execute_halopsa_sql",
                "features.tdsynnex_partner.workflows.tools",
                "modules.extensions.platform_auth",
            ):
                sys.modules.pop(name, None)

    def entry_points(self):
        files = [
            ROOT / "features" / "halopsa_reporting" / "workflows" / "execute_halopsa_sql.py",
            ROOT / "features" / "autoelevate" / "workflows" / "tools.py",
            ROOT / "features" / "tdsynnex_partner" / "workflows" / "tools.py",
            *sorted(CSP.glob("*.py")),
        ]
        for file in files:
            tree = ast.parse(file.read_text())
            functions = [
                node for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef)
                and any(
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id in ("workflow", "tool")
                    for decorator in node.decorator_list
                )
            ]
            if not functions:
                continue
            module_name = ".".join(file.relative_to(ROOT).with_suffix("").parts)
            module = importlib.import_module(module_name)
            for function in functions:
                yield module_name, getattr(module, function.name)

    def test_every_provider_wide_entry_point_rejects_ordinary_callers(self):
        seen = []
        for module_name, function in self.entry_points():
            parameters = inspect.signature(function).parameters
            arguments = {
                name: "synthetic-value"
                for name, parameter in parameters.items()
                if parameter.default is inspect.Parameter.empty
                and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            }
            with self.subTest(module=module_name, function=function.__name__):
                with self.assertRaisesRegex(UserError, "Platform administrator"):
                    asyncio.run(function(**arguments))
                seen.append(function.__name__)
        self.assertEqual(len(seen), 23)
        self.assertEqual(self.calls, [])

    def test_absent_identity_and_function_keys_fail_closed(self):
        from modules.extensions.platform_auth import require_platform_admin
        for user_id, is_admin, is_function_key in (
            (None, True, False),
            ("ordinary-user", False, False),
            ("admin-user", True, True),
        ):
            self.context.user_id = user_id
            self.context.is_platform_admin = is_admin
            self.context.is_function_key = is_function_key
            with self.subTest(user_id=user_id, is_admin=is_admin, is_function_key=is_function_key):
                with self.assertRaises(UserError):
                    require_platform_admin()

    def test_platform_admin_can_use_report_tool(self):
        self.context.user_id = "admin-user"
        self.context.is_platform_admin = True
        from features.halopsa_reporting.workflows.execute_halopsa_sql import execute_halopsa_sql
        result = asyncio.run(execute_halopsa_sql("SELECT customer FROM synthetic_report"))
        self.assertTrue(result["success"])
        self.assertEqual(result["rows"], [{"customer": "synthetic"}])
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
