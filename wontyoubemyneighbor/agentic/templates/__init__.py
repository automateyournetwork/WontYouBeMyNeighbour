"""
Template Engine Module

Provides:
- Template definitions
- Variable substitution
- Template rendering
- Configuration generation
"""

from .variables import (
    Variable,
    VariableType,
    VariableScope,
    VariableManager,
    get_variable_manager
)
from .renderer import (
    Template,
    TemplateConfig,
    TemplateCategory,
    TemplateManager,
    get_template_manager
)
from .engine import (
    RenderResult,
    TemplateEngine,
    get_template_engine
)

__all__ = [
    # Variables
    "Variable",
    "VariableType",
    "VariableScope",
    "VariableManager",
    "get_variable_manager",
    # Renderer
    "Template",
    "TemplateConfig",
    "TemplateCategory",
    "TemplateManager",
    "get_template_manager",
    # Engine
    "RenderResult",
    "TemplateEngine",
    "get_template_engine"
]
