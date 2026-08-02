"""
Base Tool Class for MCP Tools

Provides abstract base class for all LawAI MCP tools with standard interface,
error handling, and validation.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """Tool parameter definition"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any | None = None


class ToolMetadata(BaseModel):
    """Tool metadata"""
    name: str
    description: str
    parameters: dict[str, ToolParameter]
    examples: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Standard tool execution result"""
    success: bool
    data: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class BaseTool(ABC):
    """
    Abstract base class for all MCP tools.

    All tools must implement:
    - name: Tool identifier
    - description: What the tool does
    - parameters: Input parameter definitions
    - execute(): Main tool logic
    """

    def __init__(self):
        """Initialize tool with logging"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (unique identifier)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, ToolParameter]:
        """Tool parameter definitions"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute tool logic.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult with success status and data/error
        """
        pass

    def get_metadata(self) -> ToolMetadata:
        """Get tool metadata"""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            examples=getattr(self, 'examples', [])
        )

    def validate_parameters(self, **kwargs) -> tuple[bool, str | None]:
        """
        Validate input parameters against tool schema.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check required parameters
            for param_name, param_def in self.parameters.items():
                if param_def.required and param_name not in kwargs:
                    return False, f"Missing required parameter: {param_name}"

            # Check parameter types (basic validation)
            for param_name, value in kwargs.items():
                if param_name not in self.parameters:
                    self.logger.warning(f"Unknown parameter: {param_name}")
                    continue

                param_def = self.parameters[param_name]
                expected_type = param_def.type

                # Basic type checking
                if expected_type == "string" and not isinstance(value, str):
                    return False, f"Parameter {param_name} must be a string"
                elif expected_type == "integer" and not isinstance(value, int):
                    return False, f"Parameter {param_name} must be an integer"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return False, f"Parameter {param_name} must be a boolean"
                elif expected_type == "dict" and not isinstance(value, dict):
                    return False, f"Parameter {param_name} must be a dictionary"
                elif expected_type == "list" and not isinstance(value, list):
                    return False, f"Parameter {param_name} must be a list"

            return True, None

        except Exception as e:
            self.logger.error(f"Parameter validation error: {e}")
            return False, f"Validation error: {e!s}"

    async def safe_execute(self, **kwargs) -> ToolResult:
        """
        Execute tool with error handling and validation.

        Args:
            **kwargs: Tool parameters

        Returns:
            ToolResult with success/error status
        """
        try:
            # Validate parameters
            is_valid, error_msg = self.validate_parameters(**kwargs)
            if not is_valid:
                self.logger.error(f"Parameter validation failed: {error_msg}")
                return ToolResult(
                    success=False,
                    error=error_msg
                )

            # Execute tool
            self.logger.info(f"Executing tool: {self.name}")
            result = await self.execute(**kwargs)

            if result.success:
                self.logger.info(f"Tool {self.name} executed successfully")
            else:
                self.logger.warning(f"Tool {self.name} failed: {result.error}")

            return result

        except Exception as e:
            self.logger.error(f"Tool execution error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {e!s}"
            )

    def __str__(self) -> str:
        """String representation"""
        return f"Tool({self.name})"

    def __repr__(self) -> str:
        """Detailed representation"""
        return f"<Tool name='{self.name}' description='{self.description}'>"
