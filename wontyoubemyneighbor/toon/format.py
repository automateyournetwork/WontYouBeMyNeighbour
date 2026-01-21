"""
TOON Format - Serialization and Deserialization

Token Oriented Object Notation format handlers including:
- JSON-based serialization with token-efficient keys
- Compression/decompression utilities
- Schema validation
- File I/O operations
"""

import json
import gzip
import base64
from typing import Any, Dict, Type, TypeVar, Union
from pathlib import Path
from datetime import datetime

T = TypeVar('T')


class TOONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for TOON format

    Handles:
    - Dataclass objects with to_dict() method
    - Datetime objects
    - Enum values
    - Bytes objects (base64 encoded)
    """

    def default(self, obj: Any) -> Any:
        # Handle objects with to_dict method
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()

        # Handle datetime
        if isinstance(obj, datetime):
            return obj.isoformat()

        # Handle enums
        if hasattr(obj, 'value'):
            return obj.value

        # Handle bytes
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode('ascii')

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        return super().default(obj)


class TOONDecoder:
    """
    TOON format decoder with type-aware deserialization
    """

    @staticmethod
    def decode(data: str, target_type: Type[T] = None) -> Union[Dict, T]:
        """
        Decode TOON string to object

        Args:
            data: TOON format string
            target_type: Optional target type with from_dict class method

        Returns:
            Decoded object or dict
        """
        parsed = json.loads(data)

        if target_type and hasattr(target_type, 'from_dict'):
            return target_type.from_dict(parsed)

        return parsed


def serialize(obj: Any, indent: int = None, compact: bool = False) -> str:
    """
    Serialize object to TOON format string

    Args:
        obj: Object to serialize (must have to_dict method or be JSON serializable)
        indent: JSON indentation level (None for compact)
        compact: If True, use minimal whitespace

    Returns:
        TOON format string
    """
    if compact:
        # Most compact representation
        return json.dumps(obj, cls=TOONEncoder, separators=(',', ':'))
    elif indent:
        return json.dumps(obj, cls=TOONEncoder, indent=indent)
    else:
        # Readable but not wasteful
        return json.dumps(obj, cls=TOONEncoder, separators=(', ', ': '))


def deserialize(data: str, target_type: Type[T] = None) -> Union[Dict, T]:
    """
    Deserialize TOON format string to object

    Args:
        data: TOON format string
        target_type: Optional target type with from_dict class method

    Returns:
        Deserialized object or dict
    """
    return TOONDecoder.decode(data, target_type)


def compress(data: str) -> str:
    """
    Compress TOON string using gzip + base64

    Args:
        data: TOON format string

    Returns:
        Compressed string (base64 encoded)
    """
    compressed = gzip.compress(data.encode('utf-8'))
    return base64.b64encode(compressed).decode('ascii')


def decompress(data: str) -> str:
    """
    Decompress base64 + gzip compressed TOON string

    Args:
        data: Compressed string (base64 encoded)

    Returns:
        Original TOON format string
    """
    compressed = base64.b64decode(data.encode('ascii'))
    return gzip.decompress(compressed).decode('utf-8')


def validate(data: Union[str, Dict], schema_type: str = None) -> Dict[str, Any]:
    """
    Validate TOON data against schema

    Args:
        data: TOON string or dict to validate
        schema_type: Schema type ('agent', 'network', 'interface', etc.)

    Returns:
        Validation result with 'valid' bool and optional 'errors' list
    """
    from .schemas import get_schema

    # Parse if string
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return {"valid": False, "errors": [f"JSON parse error: {e}"]}

    errors = []

    # Get schema if specified
    if schema_type:
        schema = get_schema(schema_type)
        if schema:
            errors.extend(schema.validate(data))

    # Basic structure validation
    if not isinstance(data, dict):
        errors.append("Root element must be an object")

    return {
        "valid": len(errors) == 0,
        "errors": errors if errors else None
    }


def save_to_file(obj: Any, filepath: Union[str, Path], compressed: bool = False) -> bool:
    """
    Save object to TOON file with atomic write operation.

    Uses a temporary file and atomic rename to prevent corruption
    if the process is interrupted during write.

    Args:
        obj: Object to save
        filepath: Destination file path
        compressed: If True, compress the file

    Returns:
        True if successful, False on error

    Raises:
        IOError: If file operations fail
        ValueError: If serialization fails
    """
    import tempfile
    import os

    filepath = Path(filepath)

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Serialize first to catch errors before writing
        toon_str = serialize(obj, indent=2)

        # Optionally compress
        if compressed:
            toon_str = compress(toon_str)
            # Add .gz extension if not present
            if not filepath.suffix == '.gz':
                filepath = filepath.with_suffix(filepath.suffix + '.gz')

        # Write to temporary file first (atomic operation)
        # Create temp file in same directory to ensure atomic rename works
        fd, temp_path = tempfile.mkstemp(
            suffix='.tmp',
            prefix='.toon_',
            dir=filepath.parent
        )
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(toon_str)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk

            # Atomic rename (on POSIX systems)
            os.replace(temp_path, filepath)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

        return True

    except (IOError, OSError) as e:
        raise IOError(f"Failed to save file {filepath}: {e}")
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to serialize object: {e}")


def load_from_file(filepath: Union[str, Path], target_type: Type[T] = None) -> Union[Dict, T]:
    """
    Load object from TOON file with proper error handling.

    Args:
        filepath: Source file path
        target_type: Optional target type for deserialization

    Returns:
        Loaded object or dict

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
        ValueError: If content is corrupted or invalid
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"TOON file not found: {filepath}")

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        if not content.strip():
            raise ValueError(f"TOON file is empty: {filepath}")

        # Check if compressed (base64 encoded gzip starts with specific characters)
        if content.startswith('H4sI'):  # gzip magic number in base64
            try:
                content = decompress(content)
            except Exception as e:
                raise ValueError(f"Failed to decompress TOON file {filepath}: {e}")

        try:
            return deserialize(content, target_type)
        except Exception as e:
            raise ValueError(f"Failed to deserialize TOON file {filepath}: {e}")

    except IOError as e:
        raise IOError(f"Failed to read TOON file {filepath}: {e}")


def get_token_count(data: Union[str, Any]) -> int:
    """
    Estimate token count for TOON data

    Uses a simple approximation: ~4 characters per token for English text

    Args:
        data: TOON string or object

    Returns:
        Estimated token count
    """
    if not isinstance(data, str):
        data = serialize(data, compact=True)

    # Simple approximation
    return len(data) // 4


class TOONFile:
    """
    Context manager for TOON file operations

    Example:
        with TOONFile('network.toon') as toon:
            toon.data['agents'].append(new_agent)
            # Auto-saves on exit
    """

    def __init__(self, filepath: Union[str, Path], target_type: Type[T] = None):
        self.filepath = Path(filepath)
        self.target_type = target_type
        self.data = None

    def __enter__(self):
        if self.filepath.exists():
            self.data = load_from_file(self.filepath, self.target_type)
        else:
            self.data = {} if self.target_type is None else None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and self.data is not None:
            save_to_file(self.data, self.filepath)
        return False


def diff_toon(old: Union[str, Dict], new: Union[str, Dict]) -> Dict[str, Any]:
    """
    Compare two TOON objects and return differences

    Args:
        old: Original TOON data
        new: New TOON data

    Returns:
        Dict with 'added', 'removed', 'changed' keys
    """
    if isinstance(old, str):
        old = json.loads(old)
    if isinstance(new, str):
        new = json.loads(new)

    def compare_dicts(d1, d2, path=""):
        added = {}
        removed = {}
        changed = {}

        all_keys = set(d1.keys()) | set(d2.keys())

        for key in all_keys:
            current_path = f"{path}.{key}" if path else key

            if key not in d1:
                added[current_path] = d2[key]
            elif key not in d2:
                removed[current_path] = d1[key]
            elif d1[key] != d2[key]:
                if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                    nested = compare_dicts(d1[key], d2[key], current_path)
                    added.update(nested['added'])
                    removed.update(nested['removed'])
                    changed.update(nested['changed'])
                else:
                    changed[current_path] = {'old': d1[key], 'new': d2[key]}

        return {'added': added, 'removed': removed, 'changed': changed}

    return compare_dicts(old, new)


def merge_toon(base: Dict, overlay: Dict, deep: bool = True) -> Dict:
    """
    Merge two TOON dicts, with overlay taking precedence

    Args:
        base: Base TOON data
        overlay: Overlay data to merge in
        deep: If True, recursively merge nested dicts

    Returns:
        Merged dict
    """
    result = base.copy()

    for key, value in overlay.items():
        if deep and key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_toon(result[key], value, deep=True)
        else:
            result[key] = value

    return result
