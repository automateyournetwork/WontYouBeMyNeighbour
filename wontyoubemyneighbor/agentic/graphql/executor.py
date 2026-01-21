"""
GraphQL Executor - Executes GraphQL queries and mutations

Provides:
- Query parsing and validation
- Query execution
- Response formatting
- Error handling
"""

import logging
import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .schema import get_schema
from .resolvers import get_resolvers, ResolverContext

logger = logging.getLogger("GraphQLExecutor")


@dataclass
class GraphQLRequest:
    """
    A GraphQL request

    Attributes:
        query: The GraphQL query string
        variables: Query variables
        operation_name: Name of operation to execute
    """
    query: str
    variables: Dict[str, Any] = field(default_factory=dict)
    operation_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "variables": self.variables,
            "operation_name": self.operation_name
        }


@dataclass
class GraphQLError:
    """
    A GraphQL error

    Attributes:
        message: Error message
        locations: Error locations in query
        path: Path to the field with error
    """
    message: str
    locations: List[Dict[str, int]] = field(default_factory=list)
    path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {"message": self.message}
        if self.locations:
            result["locations"] = self.locations
        if self.path:
            result["path"] = self.path
        return result


@dataclass
class GraphQLResponse:
    """
    A GraphQL response

    Attributes:
        data: Response data
        errors: Any errors that occurred
        extensions: Optional extensions
    """
    data: Optional[Dict[str, Any]] = None
    errors: List[GraphQLError] = field(default_factory=list)
    extensions: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.data is not None:
            result["data"] = self.data
        if self.errors:
            result["errors"] = [e.to_dict() for e in self.errors]
        if self.extensions:
            result["extensions"] = self.extensions
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class QueryParser:
    """
    Parses GraphQL queries
    """

    def __init__(self):
        """Initialize parser"""
        # Simple regex patterns for parsing
        self._operation_pattern = re.compile(
            r'(query|mutation|subscription)\s*(\w+)?\s*(\([^)]*\))?\s*\{',
            re.IGNORECASE
        )
        self._field_pattern = re.compile(
            r'(\w+)\s*(\([^)]*\))?\s*(\{[^}]*\})?',
            re.DOTALL
        )

    def parse(self, query: str) -> Tuple[str, str, List[Dict[str, Any]]]:
        """
        Parse a GraphQL query

        Args:
            query: The query string

        Returns:
            Tuple of (operation_type, operation_name, fields)
        """
        # Clean query
        query = query.strip()

        # Detect operation type
        operation_match = self._operation_pattern.search(query)
        if operation_match:
            operation_type = operation_match.group(1).lower()
            operation_name = operation_match.group(2) or ""
        else:
            # Default to query for shorthand syntax
            operation_type = "query"
            operation_name = ""

        # Extract fields from query body
        fields = self._extract_fields(query)

        return operation_type, operation_name, fields

    def _extract_fields(self, query: str) -> List[Dict[str, Any]]:
        """Extract field selections from query"""
        fields = []

        # Find the main selection set
        start = query.find('{')
        end = query.rfind('}')
        if start == -1 or end == -1:
            return fields

        body = query[start + 1:end].strip()

        # Simple field extraction (not handling nested selections fully)
        current_field = ""
        brace_depth = 0

        for char in body:
            if char == '{':
                brace_depth += 1
                current_field += char
            elif char == '}':
                brace_depth -= 1
                current_field += char
                if brace_depth == 0:
                    field_info = self._parse_field(current_field.strip())
                    if field_info:
                        fields.append(field_info)
                    current_field = ""
            elif char == '\n' and brace_depth == 0:
                if current_field.strip():
                    field_info = self._parse_field(current_field.strip())
                    if field_info:
                        fields.append(field_info)
                current_field = ""
            else:
                current_field += char

        # Handle last field
        if current_field.strip():
            field_info = self._parse_field(current_field.strip())
            if field_info:
                fields.append(field_info)

        return fields

    def _parse_field(self, field_str: str) -> Optional[Dict[str, Any]]:
        """Parse a single field"""
        if not field_str:
            return None

        # Extract field name
        name_match = re.match(r'(\w+)', field_str)
        if not name_match:
            return None

        field_name = name_match.group(1)

        # Extract arguments
        args = {}
        args_match = re.search(r'\(([^)]+)\)', field_str)
        if args_match:
            args_str = args_match.group(1)
            # Simple argument parsing
            for arg in args_str.split(','):
                if ':' in arg:
                    key, value = arg.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    args[key] = value

        # Extract sub-fields
        sub_fields = []
        sub_match = re.search(r'\{(.+)\}', field_str, re.DOTALL)
        if sub_match:
            sub_body = sub_match.group(1)
            for line in sub_body.split('\n'):
                line = line.strip()
                if line:
                    sub_fields.append(line)

        return {
            "name": field_name,
            "args": args,
            "sub_fields": sub_fields
        }


class GraphQLExecutor:
    """
    Executes GraphQL queries and mutations
    """

    def __init__(self):
        """Initialize executor"""
        self._schema = get_schema()
        self._query_resolvers, self._mutation_resolvers = get_resolvers()
        self._parser = QueryParser()
        self._request_counter = 0

    def execute(
        self,
        request: GraphQLRequest,
        context: Optional[ResolverContext] = None
    ) -> GraphQLResponse:
        """
        Execute a GraphQL request

        Args:
            request: The GraphQL request
            context: Optional resolver context

        Returns:
            GraphQLResponse with results
        """
        self._request_counter += 1
        start_time = datetime.now()

        if context is None:
            context = ResolverContext()

        response = GraphQLResponse()

        try:
            # Parse query
            operation_type, operation_name, fields = self._parser.parse(request.query)

            # Execute based on operation type
            if operation_type == "query":
                response.data = self._execute_query(fields, request.variables, context)
            elif operation_type == "mutation":
                response.data = self._execute_mutation(fields, request.variables, context)
            elif operation_type == "subscription":
                response.errors.append(GraphQLError(
                    message="Subscriptions not supported in this implementation"
                ))
            else:
                response.errors.append(GraphQLError(
                    message=f"Unknown operation type: {operation_type}"
                ))

        except Exception as e:
            logger.error(f"GraphQL execution error: {e}")
            response.errors.append(GraphQLError(message=str(e)))

        # Add timing extension
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        response.extensions["timing"] = {
            "duration_ms": elapsed,
            "request_id": self._request_counter
        }

        return response

    def _execute_query(
        self,
        fields: List[Dict[str, Any]],
        variables: Dict[str, Any],
        context: ResolverContext
    ) -> Dict[str, Any]:
        """Execute query fields"""
        result = {}

        for field in fields:
            field_name = field.get("name")
            field_args = field.get("args", {})

            # Substitute variables
            for key, value in field_args.items():
                if isinstance(value, str) and value.startswith("$"):
                    var_name = value[1:]
                    if var_name in variables:
                        field_args[key] = variables[var_name]

            # Resolve field
            resolved = self._query_resolvers.resolve(field_name, field_args, context)
            result[field_name] = resolved

        return result

    def _execute_mutation(
        self,
        fields: List[Dict[str, Any]],
        variables: Dict[str, Any],
        context: ResolverContext
    ) -> Dict[str, Any]:
        """Execute mutation fields"""
        result = {}

        for field in fields:
            field_name = field.get("name")
            field_args = field.get("args", {})

            # Substitute variables
            for key, value in field_args.items():
                if isinstance(value, str) and value.startswith("$"):
                    var_name = value[1:]
                    if var_name in variables:
                        field_args[key] = variables[var_name]

            # Resolve mutation
            resolved = self._mutation_resolvers.resolve(field_name, field_args, context)
            result[field_name] = resolved

        return result

    def execute_string(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[ResolverContext] = None
    ) -> GraphQLResponse:
        """
        Execute a query string directly

        Args:
            query: GraphQL query string
            variables: Query variables
            context: Resolver context

        Returns:
            GraphQLResponse
        """
        request = GraphQLRequest(
            query=query,
            variables=variables or {}
        )
        return self.execute(request, context)

    def get_schema_sdl(self) -> str:
        """Get the schema as SDL"""
        return self._schema.to_sdl()

    def introspect(self) -> Dict[str, Any]:
        """Return introspection data"""
        schema = self._schema

        types = []
        for type_def in schema.get_all_types():
            types.append({
                "name": type_def.name,
                "description": type_def.description,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.field_type,
                        "description": f.description,
                        "args": f.args
                    }
                    for f in type_def.fields
                ]
            })

        enums = []
        for enum_def in schema.get_all_enums():
            enums.append({
                "name": enum_def.name,
                "description": enum_def.description,
                "values": enum_def.values
            })

        query_type = schema.get_query_type()
        mutation_type = schema.get_mutation_type()

        return {
            "__schema": {
                "types": types,
                "enums": enums,
                "queryType": {"name": query_type.name} if query_type else None,
                "mutationType": {"name": mutation_type.name} if mutation_type else None,
                "subscriptionType": None
            }
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get executor statistics"""
        return {
            "total_requests": self._request_counter,
            "schema_stats": self._schema.get_statistics()
        }


# Global executor instance
_global_executor: Optional[GraphQLExecutor] = None


def get_executor() -> GraphQLExecutor:
    """Get or create the global executor"""
    global _global_executor
    if _global_executor is None:
        _global_executor = GraphQLExecutor()
    return _global_executor
