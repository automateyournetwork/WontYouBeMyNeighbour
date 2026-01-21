"""
Template Engine

Provides:
- Template rendering
- Variable substitution
- Filter and function support
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from .variables import VariableManager, get_variable_manager
from .renderer import Template, TemplateManager, get_template_manager


@dataclass
class RenderResult:
    """Result of template rendering"""

    template_id: str
    success: bool
    output: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    variables_used: List[str] = field(default_factory=list)
    render_time_ms: float = 0.0
    rendered_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "success": self.success,
            "output": self.output,
            "errors": self.errors,
            "warnings": self.warnings,
            "variables_used": self.variables_used,
            "render_time_ms": self.render_time_ms,
            "rendered_at": self.rendered_at.isoformat()
        }


class TemplateEngine:
    """Template rendering engine"""

    def __init__(self):
        self._template_manager = get_template_manager()
        self._variable_manager = get_variable_manager()
        self._filters: Dict[str, Callable] = {}
        self._functions: Dict[str, Callable] = {}
        self._init_builtin_filters()
        self._init_builtin_functions()

    def _init_builtin_filters(self) -> None:
        """Initialize built-in filters"""

        def upper(value: str) -> str:
            return str(value).upper()

        def lower(value: str) -> str:
            return str(value).lower()

        def capitalize(value: str) -> str:
            return str(value).capitalize()

        def title(value: str) -> str:
            return str(value).title()

        def strip(value: str) -> str:
            return str(value).strip()

        def replace(value: str, old: str, new: str) -> str:
            return str(value).replace(old, new)

        def default_filter(value: Any, default: Any) -> Any:
            return value if value is not None else default

        def length(value: Any) -> int:
            return len(value) if hasattr(value, '__len__') else 0

        def join(value: list, separator: str = ",") -> str:
            return separator.join(str(v) for v in value) if isinstance(value, list) else str(value)

        def first(value: list) -> Any:
            return value[0] if value else None

        def last(value: list) -> Any:
            return value[-1] if value else None

        def sort_filter(value: list) -> list:
            return sorted(value) if isinstance(value, list) else value

        def reverse(value: Any) -> Any:
            if isinstance(value, str):
                return value[::-1]
            elif isinstance(value, list):
                return list(reversed(value))
            return value

        def indent(value: str, spaces: int = 2) -> str:
            return "\n".join(" " * spaces + line for line in str(value).split("\n"))

        def quote(value: str) -> str:
            return f'"{value}"'

        def mask(value: str, show_last: int = 4) -> str:
            if len(str(value)) <= show_last:
                return "*" * len(str(value))
            return "*" * (len(str(value)) - show_last) + str(value)[-show_last:]

        self._filters = {
            "upper": upper,
            "lower": lower,
            "capitalize": capitalize,
            "title": title,
            "strip": strip,
            "replace": replace,
            "default": default_filter,
            "length": length,
            "len": length,
            "join": join,
            "first": first,
            "last": last,
            "sort": sort_filter,
            "reverse": reverse,
            "indent": indent,
            "quote": quote,
            "mask": mask
        }

    def _init_builtin_functions(self) -> None:
        """Initialize built-in functions"""

        def now() -> str:
            return datetime.now().isoformat()

        def today() -> str:
            return datetime.now().strftime("%Y-%m-%d")

        def timestamp() -> int:
            return int(datetime.now().timestamp())

        def range_func(*args) -> list:
            return list(range(*args))

        def ip_network(ip: str, prefix: int) -> str:
            return f"{ip}/{prefix}"

        def wildcard_mask(prefix: int) -> str:
            """Convert prefix length to wildcard mask"""
            if not 0 <= prefix <= 32:
                return "0.0.0.0"
            bits = (1 << 32) - (1 << (32 - prefix))
            wildcard = (1 << 32) - 1 - bits
            return ".".join(str((wildcard >> (8 * i)) & 0xFF) for i in range(3, -1, -1))

        def subnet_mask(prefix: int) -> str:
            """Convert prefix length to subnet mask"""
            if not 0 <= prefix <= 32:
                return "255.255.255.255"
            bits = (1 << 32) - (1 << (32 - prefix))
            return ".".join(str((bits >> (8 * i)) & 0xFF) for i in range(3, -1, -1))

        def increment_ip(ip: str, increment: int = 1) -> str:
            """Increment IP address"""
            parts = ip.split(".")
            if len(parts) != 4:
                return ip
            num = sum(int(p) << (8 * (3 - i)) for i, p in enumerate(parts))
            num += increment
            return ".".join(str((num >> (8 * i)) & 0xFF) for i in range(3, -1, -1))

        self._functions = {
            "now": now,
            "today": today,
            "timestamp": timestamp,
            "range": range_func,
            "ip_network": ip_network,
            "wildcard_mask": wildcard_mask,
            "subnet_mask": subnet_mask,
            "increment_ip": increment_ip
        }

    def register_filter(
        self,
        name: str,
        filter_func: Callable
    ) -> None:
        """Register a custom filter"""
        self._filters[name] = filter_func

    def register_function(
        self,
        name: str,
        function: Callable
    ) -> None:
        """Register a custom function"""
        self._functions[name] = function

    def get_filter(self, name: str) -> Optional[Callable]:
        """Get filter by name"""
        return self._filters.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """Get function by name"""
        return self._functions.get(name)

    def get_available_filters(self) -> List[str]:
        """Get list of available filters"""
        return list(self._filters.keys())

    def get_available_functions(self) -> List[str]:
        """Get list of available functions"""
        return list(self._functions.keys())

    def render(
        self,
        template_id: str,
        context: Dict[str, Any]
    ) -> RenderResult:
        """Render a template with context"""
        template = self._template_manager.get_template(template_id)
        if not template:
            return RenderResult(
                template_id=template_id,
                success=False,
                errors=["Template not found"]
            )

        if not template.enabled:
            return RenderResult(
                template_id=template_id,
                success=False,
                errors=["Template is disabled"]
            )

        start_time = datetime.now()
        template.render_count += 1
        template.last_rendered_at = start_time

        try:
            # Add functions to context
            render_context = dict(context)
            for name, func in self._functions.items():
                if name not in render_context:
                    render_context[name] = func

            # Render template
            output, variables_used = self._render_template(template, render_context)

            end_time = datetime.now()
            render_time = (end_time - start_time).total_seconds() * 1000

            # Update statistics
            template.success_count += 1
            total = template.avg_render_time_ms * (template.render_count - 1) + render_time
            template.avg_render_time_ms = total / template.render_count

            return RenderResult(
                template_id=template_id,
                success=True,
                output=output,
                variables_used=variables_used,
                render_time_ms=render_time
            )

        except Exception as e:
            template.failure_count += 1
            return RenderResult(
                template_id=template_id,
                success=False,
                errors=[str(e)],
                render_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

    def _render_template(
        self,
        template: Template,
        context: Dict[str, Any]
    ) -> tuple:
        """Internal template rendering"""
        content = template.content
        config = template.config
        variables_used = []

        # Remove comments
        comment_pattern = re.escape(config.comment_start) + r'.*?' + re.escape(config.comment_end)
        content = re.sub(comment_pattern, '', content, flags=re.DOTALL)

        # Process conditionals
        content = self._process_conditionals(content, context, config)

        # Process loops
        content = self._process_loops(content, context, config)

        # Substitute variables
        var_pattern = re.escape(config.variable_start) + r'\s*(.+?)\s*' + re.escape(config.variable_end)

        def replace_var(match):
            expr = match.group(1)
            value, var_name = self._evaluate_expression(expr, context)
            if var_name:
                variables_used.append(var_name)
            return str(value) if value is not None else ""

        content = re.sub(var_pattern, replace_var, content)

        # Clean up whitespace if configured
        if config.trim_blocks:
            content = re.sub(r'\n\s*\n', '\n', content)

        return content.strip(), list(set(variables_used))

    def _evaluate_expression(
        self,
        expr: str,
        context: Dict[str, Any]
    ) -> tuple:
        """Evaluate a template expression"""
        # Handle filters (pipe syntax)
        if '|' in expr:
            parts = expr.split('|')
            value_expr = parts[0].strip()
            value, var_name = self._get_value(value_expr, context)

            for filter_expr in parts[1:]:
                filter_expr = filter_expr.strip()
                # Handle filter with arguments
                if '(' in filter_expr:
                    filter_name = filter_expr[:filter_expr.index('(')]
                    args_str = filter_expr[filter_expr.index('(') + 1:filter_expr.rindex(')')]
                    args = [a.strip().strip('"\'') for a in args_str.split(',') if a.strip()]
                    filter_func = self._filters.get(filter_name)
                    if filter_func:
                        value = filter_func(value, *args)
                else:
                    filter_func = self._filters.get(filter_expr)
                    if filter_func:
                        value = filter_func(value)

            return value, var_name
        else:
            return self._get_value(expr, context)

    def _get_value(
        self,
        expr: str,
        context: Dict[str, Any]
    ) -> tuple:
        """Get value from context"""
        expr = expr.strip()

        # Handle function calls
        if '(' in expr and expr.endswith(')'):
            func_name = expr[:expr.index('(')]
            args_str = expr[expr.index('(') + 1:-1]
            args = []
            if args_str:
                for arg in args_str.split(','):
                    arg = arg.strip()
                    if arg.startswith('"') or arg.startswith("'"):
                        args.append(arg.strip('"\''))
                    elif arg.isdigit():
                        args.append(int(arg))
                    elif arg in context:
                        args.append(context[arg])
                    else:
                        args.append(arg)

            func = self._functions.get(func_name) or context.get(func_name)
            if callable(func):
                return func(*args), None

        # Handle dot notation
        if '.' in expr:
            parts = expr.split('.')
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return None, parts[0]
                if value is None:
                    break
            return value, parts[0]

        # Handle array access
        if '[' in expr and ']' in expr:
            var_name = expr[:expr.index('[')]
            index_str = expr[expr.index('[') + 1:expr.index(']')]
            value = context.get(var_name)
            if value and isinstance(value, (list, tuple, dict)):
                try:
                    if isinstance(value, dict):
                        return value.get(index_str.strip('"\''), None), var_name
                    else:
                        return value[int(index_str)], var_name
                except (ValueError, IndexError, KeyError):
                    return None, var_name
            return None, var_name

        # Simple variable
        return context.get(expr), expr

    def _process_conditionals(
        self,
        content: str,
        context: Dict[str, Any],
        config
    ) -> str:
        """Process conditional blocks"""
        # Simple if/endif processing
        if_pattern = re.escape(config.block_start) + r'\s*if\s+(.+?)\s*' + re.escape(config.block_end)
        endif_pattern = re.escape(config.block_start) + r'\s*endif\s*' + re.escape(config.block_end)
        else_pattern = re.escape(config.block_start) + r'\s*else\s*' + re.escape(config.block_end)

        # Find all if blocks and process them
        while True:
            if_match = re.search(if_pattern, content)
            if not if_match:
                break

            # Find matching endif
            endif_match = re.search(endif_pattern, content[if_match.end():])
            if not endif_match:
                break

            condition_expr = if_match.group(1)
            block_content = content[if_match.end():if_match.end() + endif_match.start()]

            # Check for else
            else_match = re.search(else_pattern, block_content)
            if else_match:
                if_block = block_content[:else_match.start()]
                else_block = block_content[else_match.end():]
            else:
                if_block = block_content
                else_block = ""

            # Evaluate condition
            condition_result = self._evaluate_condition(condition_expr, context)

            # Replace block
            replacement = if_block if condition_result else else_block
            content = content[:if_match.start()] + replacement + content[if_match.end() + endif_match.end():]

        return content

    def _process_loops(
        self,
        content: str,
        context: Dict[str, Any],
        config
    ) -> str:
        """Process loop blocks"""
        for_pattern = re.escape(config.block_start) + r'\s*for\s+(\w+)\s+in\s+(.+?)\s*' + re.escape(config.block_end)
        endfor_pattern = re.escape(config.block_start) + r'\s*endfor\s*' + re.escape(config.block_end)

        while True:
            for_match = re.search(for_pattern, content)
            if not for_match:
                break

            endfor_match = re.search(endfor_pattern, content[for_match.end():])
            if not endfor_match:
                break

            loop_var = for_match.group(1)
            iterable_expr = for_match.group(2)
            loop_body = content[for_match.end():for_match.end() + endfor_match.start()]

            # Get iterable
            iterable, _ = self._get_value(iterable_expr, context)
            if not iterable:
                iterable = []

            # Render loop body for each item
            loop_output = []
            for item in iterable:
                loop_context = dict(context)
                loop_context[loop_var] = item
                rendered_body = loop_body

                # Substitute variables in loop body
                var_pattern = re.escape(config.variable_start) + r'\s*(.+?)\s*' + re.escape(config.variable_end)

                def replace_in_loop(match):
                    expr = match.group(1)
                    value, _ = self._evaluate_expression(expr, loop_context)
                    return str(value) if value is not None else ""

                rendered_body = re.sub(var_pattern, replace_in_loop, rendered_body)
                loop_output.append(rendered_body)

            replacement = "".join(loop_output)
            content = content[:for_match.start()] + replacement + content[for_match.end() + endfor_match.end():]

        return content

    def _evaluate_condition(
        self,
        expr: str,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a condition expression"""
        expr = expr.strip()

        # Handle comparison operators
        for op in [' == ', ' != ', ' >= ', ' <= ', ' > ', ' < ', ' in ', ' not in ']:
            if op in expr:
                parts = expr.split(op)
                if len(parts) == 2:
                    left, _ = self._get_value(parts[0].strip(), context)
                    right, _ = self._get_value(parts[1].strip(), context)

                    # Try to parse right side as literal if not found
                    if right is None:
                        right_str = parts[1].strip()
                        if right_str.startswith('"') or right_str.startswith("'"):
                            right = right_str.strip('"\'')
                        elif right_str.isdigit():
                            right = int(right_str)
                        elif right_str.lower() in ('true', 'false'):
                            right = right_str.lower() == 'true'

                    op = op.strip()
                    if op == '==':
                        return left == right
                    elif op == '!=':
                        return left != right
                    elif op == '>':
                        return left > right if left is not None and right is not None else False
                    elif op == '<':
                        return left < right if left is not None and right is not None else False
                    elif op == '>=':
                        return left >= right if left is not None and right is not None else False
                    elif op == '<=':
                        return left <= right if left is not None and right is not None else False
                    elif op == 'in':
                        return left in right if right is not None else False
                    elif op == 'not in':
                        return left not in right if right is not None else True

        # Simple truthy check
        value, _ = self._get_value(expr, context)
        return bool(value)

    def render_string(
        self,
        template_string: str,
        context: Dict[str, Any]
    ) -> RenderResult:
        """Render a template string directly"""
        # Create temporary template
        temp_template = Template(
            id="temp",
            name="Temporary",
            content=template_string,
            category=None
        )

        try:
            output, variables_used = self._render_template(temp_template, context)

            return RenderResult(
                template_id="temp",
                success=True,
                output=output,
                variables_used=variables_used
            )
        except Exception as e:
            return RenderResult(
                template_id="temp",
                success=False,
                errors=[str(e)]
            )

    def validate_template(
        self,
        template_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate a template"""
        template = self._template_manager.get_template(template_id)
        if not template:
            return {"valid": False, "errors": ["Template not found"]}

        errors = []
        warnings = []

        # Extract variables from template
        variables = template.extract_variables()

        # Check required variables
        context = context or {}
        missing = [v for v in variables if v not in context and v not in self._functions]
        if missing:
            warnings.append(f"Missing variables: {', '.join(missing)}")

        # Try to render with empty context to find errors
        try:
            self._render_template(template, context)
        except Exception as e:
            errors.append(str(e))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "variables": variables
        }

    def get_statistics(self) -> dict:
        """Get engine statistics"""
        return {
            "template_stats": self._template_manager.get_statistics(),
            "variable_stats": self._variable_manager.get_statistics(),
            "available_filters": len(self._filters),
            "available_functions": len(self._functions)
        }


# Global template engine instance
_template_engine: Optional[TemplateEngine] = None


def get_template_engine() -> TemplateEngine:
    """Get or create the global template engine"""
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine
