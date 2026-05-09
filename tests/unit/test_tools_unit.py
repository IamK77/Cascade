"""Unit tests for src/tools/ — the LLM-facing tool layer.

Tests the parameter validation, transformation, and delegation logic
in each tool function, with CascadeClient mocked to isolate the layer.
"""

from unittest.mock import MagicMock, patch

import pytest

from cascade.types import Contract, Result


def _ok(**data):
    return Result(success=True, message="ok", data=data)


# ---------------------------------------------------------------------------
# Tool registry (__init__.py)
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_get_all_tools_returns_12_entries(self):
        from tools import get_all_tools

        tools = get_all_tools()
        assert len(tools) == 12

    def test_get_all_tools_values_are_callable(self):
        from tools import get_all_tools

        for name, fn in get_all_tools().items():
            assert callable(fn), f"{name} is not callable"

    def test_execute_tool_delegates_correctly(self):
        from tools import execute_tool

        storage = MagicMock()
        with patch("tools.add_node.CascadeClient") as mock_cls:
            mock_cls.return_value.add.return_value = _ok()
            result = execute_tool(storage, "add_node", {"node_id": "a"})
            assert result["success"] is True

    def test_execute_tool_unknown_raises(self):
        from tools import execute_tool

        with pytest.raises(ValueError, match="Unknown tool"):
            execute_tool(MagicMock(), "nonexistent", {})


# ---------------------------------------------------------------------------
# add_node
# ---------------------------------------------------------------------------


class TestAddNode:
    def setup_method(self):
        from tools.add_node import add_node

        self.fn = add_node
        self.storage = MagicMock()

    # --- Validation (no CascadeClient needed) ---

    def test_missing_node_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "node_id" in r["message"]

    def test_empty_expectation_rejected(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [{"node_id": "a", "expectation": "", "promise": "p"}],
            },
        )
        assert r["success"] is False
        assert "expectation" in r["message"]

    def test_whitespace_expectation_rejected(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [{"node_id": "a", "expectation": "   ", "promise": "p"}],
            },
        )
        assert r["success"] is False
        assert "expectation" in r["message"]

    def test_empty_promise_rejected(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [{"node_id": "a", "expectation": "e", "promise": ""}],
            },
        )
        assert r["success"] is False
        assert "promise" in r["message"]

    def test_whitespace_promise_rejected(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [{"node_id": "a", "expectation": "e", "promise": "   "}],
            },
        )
        assert r["success"] is False
        assert "promise" in r["message"]

    def test_missing_contract_for_dependency(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [],
            },
        )
        assert r["success"] is False
        assert "Missing contract" in r["message"]
        assert r["data"]["missing_contract_for"] == "a"

    def test_missing_contract_for_dependent(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "a",
                "dependents": ["b"],
                "expectations": [],
            },
        )
        assert r["success"] is False
        assert "Missing contract" in r["message"]
        assert r["data"]["missing_contract_for"] == "b"

    def test_expectations_entry_without_node_id_skipped(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [{"expectation": "e", "promise": "p"}],
            },
        )
        assert r["success"] is False
        assert "Missing contract" in r["message"]

    # --- Happy path (mock CascadeClient) ---

    def test_add_node_no_deps(self):
        with patch("tools.add_node.CascadeClient") as mock_cls:
            mock_cls.return_value.add.return_value = _ok()
            r = self.fn(self.storage, {"node_id": "a"})
            assert r["success"] is True
            mock_cls.return_value.add.assert_called_once_with("a", deps=None, dependents=None)

    def test_add_node_with_dependencies(self):
        with patch("tools.add_node.CascadeClient") as mock_cls:
            mock_cls.return_value.add.return_value = _ok()
            r = self.fn(
                self.storage,
                {
                    "node_id": "b",
                    "dependencies": ["a"],
                    "expectations": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            )
            assert r["success"] is True
            call_args = mock_cls.return_value.add.call_args
            deps = call_args.kwargs.get("deps") or call_args[1].get("deps")
            assert "a" in deps
            assert deps["a"] == Contract(expectation="E", promise="P")

    def test_add_node_with_dependents(self):
        with patch("tools.add_node.CascadeClient") as mock_cls:
            mock_cls.return_value.add.return_value = _ok()
            r = self.fn(
                self.storage,
                {
                    "node_id": "a",
                    "dependents": ["b"],
                    "expectations": [{"node_id": "b", "expectation": "E", "promise": "P"}],
                },
            )
            assert r["success"] is True
            call_args = mock_cls.return_value.add.call_args
            dependents = call_args.kwargs.get("dependents") or call_args[1].get("dependents")
            assert "b" in dependents
            assert dependents["b"] == Contract(expectation="E", promise="P")

    def test_add_node_with_both_deps_and_dependents(self):
        with patch("tools.add_node.CascadeClient") as mock_cls:
            mock_cls.return_value.add.return_value = _ok()
            r = self.fn(
                self.storage,
                {
                    "node_id": "b",
                    "dependencies": ["a"],
                    "dependents": ["c"],
                    "expectations": [
                        {"node_id": "a", "expectation": "Ea", "promise": "Pa"},
                        {"node_id": "c", "expectation": "Ec", "promise": "Pc"},
                    ],
                },
            )
            assert r["success"] is True
            call_args = mock_cls.return_value.add.call_args
            assert call_args[1]["deps"]["a"] == Contract(expectation="Ea", promise="Pa")
            assert call_args[1]["dependents"]["c"] == Contract(expectation="Ec", promise="Pc")


# ---------------------------------------------------------------------------
# split_node
# ---------------------------------------------------------------------------


class TestSplitNode:
    def setup_method(self):
        from tools.split_node import split_node

        self.fn = split_node
        self.storage = MagicMock()

    def test_missing_parent_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "parent_id" in r["message"]

    def test_missing_new_nodes(self):
        r = self.fn(self.storage, {"parent_id": "a"})
        assert r["success"] is False
        assert "new_nodes" in r["message"]

    def test_new_nodes_not_a_list(self):
        r = self.fn(self.storage, {"parent_id": "a", "new_nodes": "bad"})
        assert r["success"] is False
        assert "non-empty list" in r["message"]

    def test_new_nodes_empty_list(self):
        r = self.fn(self.storage, {"parent_id": "a", "new_nodes": []})
        assert r["success"] is False
        assert "non-empty list" in r["message"]

    def test_new_node_missing_node_id(self):
        r = self.fn(self.storage, {"parent_id": "a", "new_nodes": [{"other": "x"}]})
        assert r["success"] is False
        assert "node_id" in r["message"]

    def test_split_delegates_to_client(self):
        with patch("tools.split_node.CascadeClient") as mock_cls:
            mock_cls.return_value.split.return_value = _ok()
            r = self.fn(
                self.storage,
                {
                    "parent_id": "p",
                    "new_nodes": [{"node_id": "c1"}, {"node_id": "c2"}],
                },
            )
            assert r["success"] is True
            mock_cls.return_value.split.assert_called_once_with("p", ["c1", "c2"], reason="")

    def test_split_with_reason(self):
        with patch("tools.split_node.CascadeClient") as mock_cls:
            mock_cls.return_value.split.return_value = _ok()
            self.fn(
                self.storage,
                {
                    "parent_id": "p",
                    "new_nodes": [{"node_id": "c1"}],
                    "reason": "too big",
                },
            )
            mock_cls.return_value.split.assert_called_once_with("p", ["c1"], reason="too big")


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------


class TestGetTask:
    def setup_method(self):
        from tools.get_task import get_task

        self.fn = get_task
        self.storage = MagicMock()

    def test_missing_agent_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "agent_id" in r["message"]

    def test_empty_agent_id(self):
        r = self.fn(self.storage, {"agent_id": ""})
        assert r["success"] is False
        assert "agent_id" in r["message"]

    def test_get_task_agent_only(self):
        with patch("tools.get_task.CascadeClient") as mock_cls:
            mock_cls.return_value.claim.return_value = _ok()
            r = self.fn(self.storage, {"agent_id": "w1"})
            assert r["success"] is True
            mock_cls.return_value.claim.assert_called_once_with(
                "w1",
                None,
                timeout=None,
                cancel_notifier=None,
            )

    def test_get_task_specific_task(self):
        with patch("tools.get_task.CascadeClient") as mock_cls:
            mock_cls.return_value.claim.return_value = _ok()
            self.fn(self.storage, {"agent_id": "w1", "task_id": "a"})
            mock_cls.return_value.claim.assert_called_once_with(
                "w1",
                "a",
                timeout=None,
                cancel_notifier=None,
            )

    def test_get_task_with_timeout(self):
        with patch("tools.get_task.CascadeClient") as mock_cls:
            mock_cls.return_value.claim.return_value = _ok()
            self.fn(self.storage, {"agent_id": "w1", "timeout": 30.0})
            mock_cls.return_value.claim.assert_called_once_with(
                "w1",
                None,
                timeout=30.0,
                cancel_notifier=None,
            )

    def test_get_task_with_cancel_notifier(self):
        notifier = MagicMock()
        with patch("tools.get_task.CascadeClient") as mock_cls:
            mock_cls.return_value.claim.return_value = _ok()
            self.fn(self.storage, {"agent_id": "w1", "cancel_notifier": notifier})
            mock_cls.return_value.claim.assert_called_once_with(
                "w1",
                None,
                timeout=None,
                cancel_notifier=notifier,
            )


# ---------------------------------------------------------------------------
# refine_node
# ---------------------------------------------------------------------------


class TestRefineNode:
    def setup_method(self):
        from tools.refine_node import refine_node

        self.fn = refine_node
        self.storage = MagicMock()

    def test_missing_node_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "node_id" in r["message"]

    def test_missing_dependency_id(self):
        r = self.fn(self.storage, {"node_id": "a"})
        assert r["success"] is False
        assert "dependency_id" in r["message"]

    def test_missing_expectation(self):
        r = self.fn(self.storage, {"node_id": "a", "dependency_id": "b"})
        assert r["success"] is False
        assert "expectation" in r["message"]

    def test_empty_expectation(self):
        r = self.fn(self.storage, {"node_id": "a", "dependency_id": "b", "expectation": ""})
        assert r["success"] is False
        assert "expectation" in r["message"]

    def test_whitespace_expectation(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "a",
                "dependency_id": "b",
                "expectation": "   ",
            },
        )
        assert r["success"] is False
        assert "expectation" in r["message"]

    def test_missing_promise(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "a",
                "dependency_id": "b",
                "expectation": "E",
            },
        )
        assert r["success"] is False
        assert "promise" in r["message"]

    def test_empty_promise(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "a",
                "dependency_id": "b",
                "expectation": "E",
                "promise": "",
            },
        )
        assert r["success"] is False
        assert "promise" in r["message"]

    def test_whitespace_promise(self):
        r = self.fn(
            self.storage,
            {
                "node_id": "a",
                "dependency_id": "b",
                "expectation": "E",
                "promise": "   ",
            },
        )
        assert r["success"] is False
        assert "promise" in r["message"]

    def test_refine_delegates_to_client(self):
        with patch("tools.refine_node.CascadeClient") as mock_cls:
            mock_cls.return_value.refine.return_value = _ok()
            r = self.fn(
                self.storage,
                {
                    "node_id": "b",
                    "dependency_id": "a",
                    "expectation": "E",
                    "promise": "P",
                },
            )
            assert r["success"] is True
            mock_cls.return_value.refine.assert_called_once_with("b", "a", "E", "P", reason="")

    def test_refine_with_reason(self):
        with patch("tools.refine_node.CascadeClient") as mock_cls:
            mock_cls.return_value.refine.return_value = _ok()
            self.fn(
                self.storage,
                {
                    "node_id": "b",
                    "dependency_id": "a",
                    "expectation": "E",
                    "promise": "P",
                    "reason": "needed",
                },
            )
            mock_cls.return_value.refine.assert_called_once_with(
                "b",
                "a",
                "E",
                "P",
                reason="needed",
            )


# ---------------------------------------------------------------------------
# rework
# ---------------------------------------------------------------------------


class TestRework:
    VALID_PARAMS = {
        "source_node_id": "s",
        "corrective_node_id": "c",
        "reason": "wrong output",
        "agent_id": "a1",
        "source_expectation": "se",
        "source_promise": "sp",
        "corrective_expectation": "ce",
        "corrective_promise": "cp",
    }

    def setup_method(self):
        from tools.rework import rework

        self.fn = rework
        self.storage = MagicMock()

    @pytest.mark.parametrize(
        "field",
        [
            "source_node_id",
            "corrective_node_id",
            "reason",
            "agent_id",
            "source_expectation",
            "source_promise",
            "corrective_expectation",
            "corrective_promise",
        ],
    )
    def test_missing_required_field(self, field):
        params = {k: v for k, v in self.VALID_PARAMS.items() if k != field}
        r = self.fn(self.storage, params)
        assert r["success"] is False
        assert field in r["message"]

    def test_empty_string_field_rejected(self):
        params = {**self.VALID_PARAMS, "reason": ""}
        r = self.fn(self.storage, params)
        assert r["success"] is False
        assert "reason" in r["message"]

    def test_rework_delegates_to_client(self):
        with patch("tools.rework.CascadeClient") as mock_cls:
            mock_cls.return_value.rework.return_value = _ok()
            r = self.fn(self.storage, self.VALID_PARAMS)
            assert r["success"] is True
            mock_cls.return_value.rework.assert_called_once_with(
                source="s",
                corrective="c",
                reason="wrong output",
                agent_id="a1",
                source_expectation="se",
                source_promise="sp",
                corrective_expectation="ce",
                corrective_promise="cp",
            )


# ---------------------------------------------------------------------------
# check_task
# ---------------------------------------------------------------------------


class TestCheckTask:
    def setup_method(self):
        from tools.check_task import check_task

        self.fn = check_task
        self.storage = MagicMock()

    def test_missing_task_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "task_id" in r["message"]

    def test_empty_task_id(self):
        r = self.fn(self.storage, {"task_id": ""})
        assert r["success"] is False
        assert "task_id" in r["message"]

    def test_check_delegates_to_client(self):
        with patch("tools.check_task.CascadeClient") as mock_cls:
            mock_cls.return_value.check.return_value = _ok()
            r = self.fn(self.storage, {"task_id": "a"})
            assert r["success"] is True
            mock_cls.return_value.check.assert_called_once_with("a")


# ---------------------------------------------------------------------------
# check_timeouts
# ---------------------------------------------------------------------------


class TestCheckTimeouts:
    def setup_method(self):
        from tools.check_timeouts import check_timeouts

        self.fn = check_timeouts
        self.storage = MagicMock()

    def test_no_params(self):
        with patch("tools.check_timeouts.CascadeClient") as mock_cls:
            mock_cls.return_value.check_timeouts.return_value = _ok()
            r = self.fn(self.storage, {})
            assert r["success"] is True
            mock_cls.return_value.check_timeouts.assert_called_once_with(default_timeout=None)

    def test_with_default_timeout(self):
        with patch("tools.check_timeouts.CascadeClient") as mock_cls:
            mock_cls.return_value.check_timeouts.return_value = _ok()
            self.fn(self.storage, {"default_timeout": 60.0})
            mock_cls.return_value.check_timeouts.assert_called_once_with(default_timeout=60.0)


# ---------------------------------------------------------------------------
# edit_node
# ---------------------------------------------------------------------------


class TestEditNode:
    def setup_method(self):
        from tools.edit_node import edit_node

        self.fn = edit_node
        self.storage = MagicMock()

    def test_missing_node_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "node_id" in r["message"]

    def test_edit_defaults(self):
        with patch("tools.edit_node.CascadeClient") as mock_cls:
            mock_cls.return_value.edit.return_value = _ok()
            r = self.fn(self.storage, {"node_id": "a"})
            assert r["success"] is True
            mock_cls.return_value.edit.assert_called_once_with(
                "a",
                state="",
                summary="",
                critical=None,
                artifacts="",
                context_merge="merge",
                reason="",
            )

    def test_edit_all_params(self):
        with patch("tools.edit_node.CascadeClient") as mock_cls:
            mock_cls.return_value.edit.return_value = _ok()
            self.fn(
                self.storage,
                {
                    "node_id": "a",
                    "state": "READY",
                    "summary": "done",
                    "critical": {"k": "v"},
                    "artifacts": "file.txt",
                    "context_merge": "replace",
                    "reason": "fix",
                },
            )
            mock_cls.return_value.edit.assert_called_once_with(
                "a",
                state="READY",
                summary="done",
                critical={"k": "v"},
                artifacts="file.txt",
                context_merge="replace",
                reason="fix",
            )


# ---------------------------------------------------------------------------
# finish_task
# ---------------------------------------------------------------------------


class TestFinishTask:
    def setup_method(self):
        from tools.finish_task import finish_task

        self.fn = finish_task
        self.storage = MagicMock()

    def test_missing_task_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "task_id" in r["message"]

    # --- Complete path (default) ---

    def test_complete_default(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.complete.return_value = _ok()
            r = self.fn(self.storage, {"task_id": "a"})
            assert r["success"] is True
            mock_cls.return_value.complete.assert_called_once_with(
                "a",
                summary="",
                critical=None,
                artifacts="",
                deliverables=None,
            )

    def test_complete_with_all_fields(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.complete.return_value = _ok()
            self.fn(
                self.storage,
                {
                    "task_id": "a",
                    "success": True,
                    "summary": "done",
                    "critical": {"k": "v"},
                    "artifacts": "code",
                    "deliverables": {"b": "output"},
                },
            )
            mock_cls.return_value.complete.assert_called_once_with(
                "a",
                summary="done",
                critical={"k": "v"},
                artifacts="code",
                deliverables={"b": "output"},
            )

    def test_complete_backward_compat_result_field(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.complete.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "result": "legacy"})
            call_args = mock_cls.return_value.complete.call_args
            assert call_args[1]["summary"] == "legacy"

    # --- Fail path ---

    def test_fail_basic(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.fail.return_value = _ok()
            r = self.fn(self.storage, {"task_id": "a", "success": False})
            assert r["success"] is True
            mock_cls.return_value.fail.assert_called_once_with("a", reason="", cascade=False)

    def test_fail_with_cascade(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.fail.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "success": False, "cascade": True})
            mock_cls.return_value.fail.assert_called_once_with("a", reason="", cascade=True)

    def test_fail_with_reason(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.fail.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "success": False, "summary": "oom"})
            mock_cls.return_value.fail.assert_called_once_with("a", reason="oom", cascade=False)

    # --- Release path ---

    def test_release_basic(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.release.return_value = _ok()
            r = self.fn(self.storage, {"task_id": "a", "release": True})
            assert r["success"] is True
            mock_cls.return_value.release.assert_called_once_with("a", reason="")

    def test_release_with_summary(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.release.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "release": True, "summary": "blocked"})
            mock_cls.return_value.release.assert_called_once_with("a", reason="blocked")

    def test_release_uses_result_as_fallback(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.release.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "release": True, "result": "old-api"})
            mock_cls.return_value.release.assert_called_once_with("a", reason="old-api")

    def test_release_true_ignores_success_true(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.release.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "release": True, "success": True})
            mock_cls.return_value.release.assert_called_once()
            mock_cls.return_value.complete.assert_not_called()

    def test_release_false_success_false_goes_to_fail(self):
        with patch("tools.finish_task.CascadeClient") as mock_cls:
            mock_cls.return_value.fail.return_value = _ok()
            self.fn(self.storage, {"task_id": "a", "release": False, "success": False})
            mock_cls.return_value.fail.assert_called_once()
            mock_cls.return_value.release.assert_not_called()


# ---------------------------------------------------------------------------
# remove_node
# ---------------------------------------------------------------------------


class TestRemoveNode:
    def setup_method(self):
        from tools.remove_node import remove_node

        self.fn = remove_node
        self.storage = MagicMock()

    def test_missing_node_id(self):
        r = self.fn(self.storage, {})
        assert r["success"] is False
        assert "node_id" in r["message"]

    def test_remove_defaults(self):
        with patch("tools.remove_node.CascadeClient") as mock_cls:
            mock_cls.return_value.remove.return_value = _ok()
            r = self.fn(self.storage, {"node_id": "a"})
            assert r["success"] is True
            mock_cls.return_value.remove.assert_called_once_with("a", cascade=False, reason="")

    def test_remove_with_cascade_and_reason(self):
        with patch("tools.remove_node.CascadeClient") as mock_cls:
            mock_cls.return_value.remove.return_value = _ok()
            self.fn(self.storage, {"node_id": "a", "cascade": True, "reason": "obsolete"})
            mock_cls.return_value.remove.assert_called_once_with(
                "a",
                cascade=True,
                reason="obsolete",
            )


# ---------------------------------------------------------------------------
# list_nodes
# ---------------------------------------------------------------------------


class TestListNodes:
    def setup_method(self):
        from tools.list_nodes import list_nodes

        self.fn = list_nodes
        self.storage = MagicMock()

    def test_list_defaults(self):
        with patch("tools.list_nodes.CascadeClient") as mock_cls:
            mock_cls.return_value.nodes.return_value = _ok()
            r = self.fn(self.storage, {})
            assert r["success"] is True
            mock_cls.return_value.nodes.assert_called_once_with(
                state=None,
                include_pending_only=False,
            )

    def test_list_with_state_filter(self):
        with patch("tools.list_nodes.CascadeClient") as mock_cls:
            mock_cls.return_value.nodes.return_value = _ok()
            self.fn(self.storage, {"state_filter": "READY"})
            mock_cls.return_value.nodes.assert_called_once_with(
                state="READY",
                include_pending_only=False,
            )

    def test_list_with_pending_only(self):
        with patch("tools.list_nodes.CascadeClient") as mock_cls:
            mock_cls.return_value.nodes.return_value = _ok()
            self.fn(self.storage, {"include_pending_only": True})
            mock_cls.return_value.nodes.assert_called_once_with(
                state=None,
                include_pending_only=True,
            )


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


class TestHistory:
    def setup_method(self):
        from tools.history import history

        self.fn = history
        self.storage = MagicMock()

    def test_history_defaults(self):
        with patch("tools.history.CascadeClient") as mock_cls:
            mock_cls.return_value.history.return_value = _ok()
            r = self.fn(self.storage, {})
            assert r["success"] is True
            mock_cls.return_value.history.assert_called_once_with(
                node_id="",
                event_type="",
                last_n=0,
                summary=False,
            )

    def test_history_with_node_filter(self):
        with patch("tools.history.CascadeClient") as mock_cls:
            mock_cls.return_value.history.return_value = _ok()
            self.fn(self.storage, {"node_id": "a"})
            assert mock_cls.return_value.history.call_args[1]["node_id"] == "a"

    def test_history_with_event_type(self):
        with patch("tools.history.CascadeClient") as mock_cls:
            mock_cls.return_value.history.return_value = _ok()
            self.fn(self.storage, {"event_type": "NODE_ADDED"})
            assert mock_cls.return_value.history.call_args[1]["event_type"] == "NODE_ADDED"

    def test_history_with_last_n(self):
        with patch("tools.history.CascadeClient") as mock_cls:
            mock_cls.return_value.history.return_value = _ok()
            self.fn(self.storage, {"last_n": 5})
            assert mock_cls.return_value.history.call_args[1]["last_n"] == 5

    def test_history_with_summary(self):
        with patch("tools.history.CascadeClient") as mock_cls:
            mock_cls.return_value.history.return_value = _ok()
            self.fn(self.storage, {"summary": True})
            assert mock_cls.return_value.history.call_args[1]["summary"] is True
