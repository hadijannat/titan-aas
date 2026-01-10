"""Tests for plugin hooks."""

from titan.plugins.hooks import (
    HOOK_METADATA,
    HookContext,
    HookResult,
    HookResultType,
    HookType,
)


class TestHookType:
    """Tests for HookType enum."""

    def test_all_crud_hooks_exist(self) -> None:
        """All CRUD operation hooks are defined."""
        # Shell hooks
        assert HookType.PRE_CREATE_SHELL
        assert HookType.POST_CREATE_SHELL
        assert HookType.PRE_UPDATE_SHELL
        assert HookType.POST_UPDATE_SHELL
        assert HookType.PRE_DELETE_SHELL
        assert HookType.POST_DELETE_SHELL

        # Submodel hooks
        assert HookType.PRE_CREATE_SUBMODEL
        assert HookType.POST_CREATE_SUBMODEL
        assert HookType.PRE_UPDATE_SUBMODEL
        assert HookType.POST_UPDATE_SUBMODEL
        assert HookType.PRE_DELETE_SUBMODEL
        assert HookType.POST_DELETE_SUBMODEL

    def test_lifecycle_hooks_exist(self) -> None:
        """Lifecycle hooks are defined."""
        assert HookType.ON_STARTUP
        assert HookType.ON_SHUTDOWN

    def test_request_hooks_exist(self) -> None:
        """Request lifecycle hooks are defined."""
        assert HookType.PRE_REQUEST
        assert HookType.POST_REQUEST


class TestHookResult:
    """Tests for HookResult."""

    def test_proceed_result(self) -> None:
        """HookResult.proceed() creates proceed result."""
        result = HookResult.proceed()

        assert result.result_type == HookResultType.PROCEED
        assert result.data is None
        assert result.error_message is None

    def test_proceed_with_data(self) -> None:
        """HookResult.proceed() can include data."""
        result = HookResult.proceed(data={"modified": True})

        assert result.result_type == HookResultType.PROCEED
        assert result.data == {"modified": True}

    def test_abort_result(self) -> None:
        """HookResult.abort() creates abort result."""
        result = HookResult.abort("Validation failed", code=400)

        assert result.result_type == HookResultType.ABORT
        assert result.error_message == "Validation failed"
        assert result.error_code == 400

    def test_abort_default_code(self) -> None:
        """HookResult.abort() has default error code."""
        result = HookResult.abort("Error")

        assert result.error_code == 400

    def test_modify_result(self) -> None:
        """HookResult.modify() creates modify result."""
        result = HookResult.modify(data={"key": "value"})

        assert result.result_type == HookResultType.MODIFY
        assert result.data == {"key": "value"}


class TestHookContext:
    """Tests for HookContext."""

    def test_context_creation(self) -> None:
        """HookContext can be created."""
        ctx = HookContext(
            hook_type=HookType.PRE_CREATE_SHELL,
            data={"shell": {"id": "test"}},
        )

        assert ctx.hook_type == HookType.PRE_CREATE_SHELL
        assert ctx.data == {"shell": {"id": "test"}}

    def test_context_get(self) -> None:
        """Context.get() retrieves data values."""
        ctx = HookContext(
            hook_type=HookType.PRE_CREATE_SHELL,
            data={"shell": {"id": "test"}},
        )

        assert ctx.get("shell") == {"id": "test"}
        assert ctx.get("missing") is None
        assert ctx.get("missing", "default") == "default"

    def test_context_set(self) -> None:
        """Context.set() updates data values."""
        ctx = HookContext(
            hook_type=HookType.PRE_CREATE_SHELL,
            data={},
        )

        ctx.set("validated", True)

        assert ctx.data["validated"] is True
        assert ctx.get("validated") is True

    def test_context_metadata(self) -> None:
        """Context can include metadata."""
        ctx = HookContext(
            hook_type=HookType.PRE_REQUEST,
            metadata={"trace_id": "abc123"},
        )

        assert ctx.metadata["trace_id"] == "abc123"


class TestHookMetadata:
    """Tests for hook metadata documentation."""

    def test_all_hooks_have_metadata(self) -> None:
        """All hook types have documentation metadata."""
        documented_hooks = set(HOOK_METADATA.keys())

        # Check key hooks are documented
        assert HookType.PRE_CREATE_SHELL in documented_hooks
        assert HookType.POST_CREATE_SHELL in documented_hooks
        assert HookType.ON_STARTUP in documented_hooks

    def test_metadata_has_description(self) -> None:
        """Hook metadata includes description."""
        for hook_type, metadata in HOOK_METADATA.items():
            assert "description" in metadata, f"Missing description for {hook_type}"

    def test_metadata_has_context(self) -> None:
        """Hook metadata includes context info."""
        for hook_type, metadata in HOOK_METADATA.items():
            assert "context" in metadata, f"Missing context for {hook_type}"
