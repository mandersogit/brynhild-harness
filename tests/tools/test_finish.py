"""Tests for the Finish tool."""

import pytest as _pytest

import brynhild.tools.finish as finish


class TestFinishTool:
    """Tests for FinishTool."""

    @_pytest.fixture
    def tool(self) -> finish.FinishTool:
        """Create a FinishTool instance."""
        return finish.FinishTool()

    def test_name(self, tool: finish.FinishTool) -> None:
        """Test tool name."""
        assert tool.name == "Finish"

    def test_description(self, tool: finish.FinishTool) -> None:
        """Test tool description."""
        assert "finish" in tool.description.lower()
        assert "status" in tool.description.lower()

    def test_requires_no_permission(self, tool: finish.FinishTool) -> None:
        """Test that Finish doesn't require permission."""
        assert tool.requires_permission is False

    def test_risk_level_is_read_only(self, tool: finish.FinishTool) -> None:
        """Test that Finish has read_only risk level."""
        assert tool.risk_level == "read_only"

    def test_input_schema_has_required_fields(self, tool: finish.FinishTool) -> None:
        """Test input schema has status and summary as required."""
        schema = tool.input_schema
        assert "properties" in schema
        assert "status" in schema["properties"]
        assert "summary" in schema["properties"]
        assert "required" in schema
        assert "status" in schema["required"]
        assert "summary" in schema["required"]

    def test_status_enum_values(self, tool: finish.FinishTool) -> None:
        """Test that status has expected enum values."""
        schema = tool.input_schema
        status_prop = schema["properties"]["status"]
        assert "enum" in status_prop
        assert "success" in status_prop["enum"]
        assert "partial" in status_prop["enum"]
        assert "failed" in status_prop["enum"]
        assert "blocked" in status_prop["enum"]

    @_pytest.mark.asyncio
    async def test_execute_success(self, tool: finish.FinishTool) -> None:
        """Test execute with success status."""
        result = await tool.execute(
            {
                "status": "success",
                "summary": "Task completed successfully",
            }
        )
        assert result.success is True
        assert "Status: success" in result.output
        assert "Summary: Task completed successfully" in result.output

    @_pytest.mark.asyncio
    async def test_execute_with_next_steps(self, tool: finish.FinishTool) -> None:
        """Test execute with next_steps."""
        result = await tool.execute(
            {
                "status": "partial",
                "summary": "Made some progress",
                "next_steps": "Continue with step 2",
            }
        )
        assert result.success is True
        assert "Status: partial" in result.output
        assert "Next steps: Continue with step 2" in result.output

    @_pytest.mark.asyncio
    async def test_execute_failed_status(self, tool: finish.FinishTool) -> None:
        """Test execute with failed status."""
        result = await tool.execute(
            {
                "status": "failed",
                "summary": "Could not complete task",
            }
        )
        assert result.success is True  # The tool always succeeds
        assert "Status: failed" in result.output

    @_pytest.mark.asyncio
    async def test_execute_blocked_status(self, tool: finish.FinishTool) -> None:
        """Test execute with blocked status."""
        result = await tool.execute(
            {
                "status": "blocked",
                "summary": "Need user input",
            }
        )
        assert result.success is True
        assert "Status: blocked" in result.output

    @_pytest.mark.asyncio
    async def test_execute_defaults(self, tool: finish.FinishTool) -> None:
        """Test execute with missing fields uses defaults."""
        result = await tool.execute({})
        assert result.success is True
        assert "Status: success" in result.output
        assert "Summary: Task completed." in result.output
