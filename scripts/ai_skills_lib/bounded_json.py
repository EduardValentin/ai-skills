"""Strict JSON parsing under shared resource and scalar limits."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math


DEFAULT_MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
DEFAULT_MAXIMUM_JSON_NODES = 100_000
DEFAULT_MAXIMUM_JSON_DEPTH = 64


class BoundedJsonError(ValueError):
    """JSON input is invalid or exceeds the shared parser resource policy."""

    def __init__(self, message: str, *, kind: str = "invalid") -> None:
        super().__init__(message)
        self.kind = kind


class JsonPreflightError(ValueError):
    """Strict JSON tokenization failed before object graph construction."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def strict_bounded_json_loads(
    value: str | bytes,
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_JSON_BYTES,
    maximum_nodes: int = DEFAULT_MAXIMUM_JSON_NODES,
    maximum_depth: int = DEFAULT_MAXIMUM_JSON_DEPTH,
    maximum_scalar_bytes: int | None = None,
    maximum_number_characters: int | None = None,
) -> object:
    """Parse strict JSON under shared byte, structure, and scalar limits."""
    _validate_limits(
        maximum_bytes=maximum_bytes,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
        maximum_number_characters=maximum_number_characters,
    )
    if not isinstance(value, (str, bytes)):
        raise BoundedJsonError(
            "JSON input must be text or bytes",
            kind="input",
        )
    try:
        size = len(value.encode("utf-8")) if isinstance(value, str) else len(value)
    except (UnicodeEncodeError, MemoryError) as error:
        raise BoundedJsonError(
            "JSON input could not be bounded",
            kind="encoding",
        ) from error
    if size > maximum_bytes:
        raise BoundedJsonError(
            "JSON input exceeds the byte limit",
            kind="bytes",
        )
    try:
        text = value.decode("utf-8") if isinstance(value, bytes) else value
    except (UnicodeDecodeError, MemoryError) as error:
        raise BoundedJsonError(
            "JSON input is invalid or exceeds parser limits",
            kind="encoding",
        ) from error

    try:
        preflight_bounded_json_structure(
            text,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
            maximum_scalar_bytes=maximum_scalar_bytes,
            maximum_number_characters=maximum_number_characters,
        )
    except JsonPreflightError as error:
        raise _bounded_error_for_kind(error.kind) from error

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, item in pairs:
            if key in document:
                raise BoundedJsonError(
                    "JSON input contains a duplicate object key",
                    kind="duplicate",
                )
            document[key] = item
        return document

    def bounded_integer(token: str) -> int:
        if (
            maximum_number_characters is not None
            and len(token) > maximum_number_characters
        ):
            raise BoundedJsonError(
                "JSON input exceeds the scalar limit",
                kind="scalar",
            )
        return int(token)

    def bounded_float(token: str) -> float:
        if (
            maximum_number_characters is not None
            and len(token) > maximum_number_characters
        ):
            raise BoundedJsonError(
                "JSON input exceeds the scalar limit",
                kind="scalar",
            )
        parsed = float(token)
        if not math.isfinite(parsed):
            raise BoundedJsonError(
                "JSON input contains a non-finite number",
                kind="nonfinite",
            )
        return parsed

    def reject_constant(_: str) -> object:
        raise BoundedJsonError(
            "JSON input contains a non-finite number",
            kind="nonfinite",
        )

    try:
        document = json.loads(
            text,
            parse_constant=reject_constant,
            parse_int=bounded_integer,
            parse_float=bounded_float,
            object_pairs_hook=reject_duplicate_keys,
        )
    except BoundedJsonError:
        raise
    except (
        json.JSONDecodeError,
        UnicodeError,
        RecursionError,
        ValueError,
        OverflowError,
        MemoryError,
        SystemError,
    ) as error:
        raise BoundedJsonError(
            "JSON input is invalid or exceeds parser limits",
            kind="invalid",
        ) from error

    validate_bounded_json_value(
        document,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
        maximum_number_characters=maximum_number_characters,
    )
    return document


def validate_bounded_json_value(
    document: object,
    *,
    maximum_nodes: int = DEFAULT_MAXIMUM_JSON_NODES,
    maximum_depth: int = DEFAULT_MAXIMUM_JSON_DEPTH,
    maximum_scalar_bytes: int | None = None,
    maximum_number_characters: int | None = None,
) -> None:
    """Validate an already materialized JSON value under the shared limits."""
    _validate_limits(
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
        maximum_number_characters=maximum_number_characters,
    )
    nodes = 0
    pending: list[tuple[object, int]] = [(document, 1)]
    try:
        while pending:
            item, depth = pending.pop()
            if depth > maximum_depth:
                raise _bounded_error_for_kind("depth")
            nodes += 1
            if nodes > maximum_nodes:
                raise _bounded_error_for_kind("nodes")
            if isinstance(item, Mapping):
                if len(item) > maximum_nodes - nodes:
                    raise _bounded_error_for_kind("nodes")
                for key, child in item.items():
                    nodes += 1
                    if nodes > maximum_nodes:
                        raise _bounded_error_for_kind("nodes")
                    _validate_json_scalar(
                        key,
                        maximum_scalar_bytes=maximum_scalar_bytes,
                        maximum_number_characters=maximum_number_characters,
                    )
                    pending.append((child, depth + 1))
            elif isinstance(item, list):
                if len(item) > maximum_nodes - nodes:
                    raise _bounded_error_for_kind("nodes")
                pending.extend((child, depth + 1) for child in item)
            else:
                _validate_json_scalar(
                    item,
                    maximum_scalar_bytes=maximum_scalar_bytes,
                    maximum_number_characters=maximum_number_characters,
                )
    except BoundedJsonError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        UnicodeError,
        ValueError,
    ) as error:
        raise BoundedJsonError(
            "JSON input exceeds bounded structure limits",
            kind="invalid",
        ) from error


def preflight_bounded_json_structure(
    text: str,
    *,
    maximum_nodes: int,
    maximum_depth: int,
    maximum_scalar_bytes: int | None = None,
    maximum_number_characters: int | None = None,
) -> None:
    """Validate strict JSON structure and limits without building its value graph."""
    _validate_limits(
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
        maximum_number_characters=maximum_number_characters,
    )
    if not isinstance(text, str):
        raise ValueError("JSON preflight input must be text")
    scanner = _BoundedJsonScanner(
        text=text,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
        maximum_number_characters=maximum_number_characters,
    )
    try:
        scanner.scan()
    except JsonPreflightError:
        raise
    except (MemoryError, OverflowError, RecursionError, SystemError) as error:
        raise JsonPreflightError("invalid") from error


def _validate_limits(
    *,
    maximum_bytes: int | None = None,
    maximum_nodes: int,
    maximum_depth: int,
    maximum_scalar_bytes: int | None,
    maximum_number_characters: int | None,
) -> None:
    limits = (maximum_nodes, maximum_depth)
    if maximum_bytes is not None:
        limits = (maximum_bytes, *limits)
    if (
        any(limit <= 0 for limit in limits)
        or maximum_scalar_bytes is not None
        and maximum_scalar_bytes <= 0
        or maximum_number_characters is not None
        and maximum_number_characters <= 0
    ):
        raise ValueError("JSON parser limits must be positive")


def _bounded_error_for_kind(kind: str) -> BoundedJsonError:
    messages = {
        "bytes": "JSON input exceeds the byte limit",
        "depth": "JSON input exceeds the depth limit",
        "nodes": "JSON input exceeds the node limit",
        "scalar": "JSON input exceeds the scalar limit",
        "nonfinite": "JSON input contains a non-finite number",
    }
    return BoundedJsonError(
        messages.get(kind, "JSON input is invalid or exceeds parser limits"),
        kind=kind,
    )


def _validate_json_scalar(
    value: object,
    *,
    maximum_scalar_bytes: int | None,
    maximum_number_characters: int | None,
) -> None:
    if isinstance(value, str):
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise BoundedJsonError(
                "JSON input contains an invalid Unicode scalar",
                kind="invalid",
            ) from error
        if (
            maximum_scalar_bytes is not None
            and size > maximum_scalar_bytes
        ):
            raise _bounded_error_for_kind("scalar")
        return
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if (
            maximum_number_characters is not None
            and value.bit_length() > maximum_number_characters * 4
        ):
            raise _bounded_error_for_kind("scalar")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise _bounded_error_for_kind("nonfinite")
        return
    raise BoundedJsonError(
        "JSON input contains a non-JSON scalar",
        kind="invalid",
    )


@dataclass
class _BoundedJsonScanner:
    text: str
    maximum_nodes: int
    maximum_depth: int
    maximum_scalar_bytes: int | None
    maximum_number_characters: int | None
    index: int = 0
    nodes: int = 0

    def scan(self) -> None:
        self._skip_whitespace()
        self._scan_value(1)
        self._skip_whitespace()
        if self.index != len(self.text):
            raise JsonPreflightError("invalid")

    def _scan_value(self, depth: int) -> None:
        if depth > self.maximum_depth:
            raise JsonPreflightError("depth")
        self._count_node()
        if self.index >= len(self.text):
            raise JsonPreflightError("invalid")
        marker = self.text[self.index]
        if marker == "{":
            self._scan_object(depth)
            return
        if marker == "[":
            self._scan_array(depth)
            return
        if marker == '"':
            self._scan_string()
            return
        for literal in ("true", "false", "null"):
            if self.text.startswith(literal, self.index):
                self.index += len(literal)
                return
        if self.text.startswith(("NaN", "Infinity", "-Infinity"), self.index):
            raise JsonPreflightError("nonfinite")
        if marker == "-" or marker.isdigit():
            self._scan_number()
            return
        raise JsonPreflightError("invalid")

    def _scan_object(self, depth: int) -> None:
        self.index += 1
        self._skip_whitespace()
        if self._consume_if("}"):
            return
        while True:
            if self.index >= len(self.text) or self.text[self.index] != '"':
                raise JsonPreflightError("invalid")
            self._count_node()
            self._scan_string()
            self._skip_whitespace()
            if not self._consume_if(":"):
                raise JsonPreflightError("invalid")
            self._skip_whitespace()
            self._scan_value(depth + 1)
            self._skip_whitespace()
            if self._consume_if("}"):
                return
            if not self._consume_if(","):
                raise JsonPreflightError("invalid")
            self._skip_whitespace()

    def _scan_array(self, depth: int) -> None:
        self.index += 1
        self._skip_whitespace()
        if self._consume_if("]"):
            return
        while True:
            self._scan_value(depth + 1)
            self._skip_whitespace()
            if self._consume_if("]"):
                return
            if not self._consume_if(","):
                raise JsonPreflightError("invalid")
            self._skip_whitespace()

    def _scan_string(self) -> None:
        self.index += 1
        decoded_bytes = 0
        while self.index < len(self.text):
            character = self.text[self.index]
            if character == '"':
                self.index += 1
                return
            if ord(character) < 0x20:
                raise JsonPreflightError("invalid")
            if character != "\\":
                decoded_bytes += _json_code_point_bytes(ord(character))
                self.index += 1
            else:
                self.index += 1
                if self.index >= len(self.text):
                    raise JsonPreflightError("invalid")
                escape = self.text[self.index]
                if escape in '"\\/bfnrt':
                    decoded_bytes += 1
                    self.index += 1
                elif escape == "u":
                    code_point = self._scan_unicode_escape()
                    if (
                        0xD800 <= code_point <= 0xDBFF
                        and self.text.startswith("\\u", self.index)
                        and self.index + 6 <= len(self.text)
                    ):
                        low_token = self.text[self.index + 2 : self.index + 6]
                        if all(
                            value in "0123456789abcdefABCDEF"
                            for value in low_token
                        ):
                            low = int(low_token, 16)
                            if 0xDC00 <= low <= 0xDFFF:
                                self.index += 6
                                decoded_bytes += 4
                            else:
                                decoded_bytes += 3
                        else:
                            decoded_bytes += 3
                    else:
                        decoded_bytes += _json_code_point_bytes(code_point)
                else:
                    raise JsonPreflightError("invalid")
            if (
                self.maximum_scalar_bytes is not None
                and decoded_bytes > self.maximum_scalar_bytes
            ):
                raise JsonPreflightError("scalar")
        raise JsonPreflightError("invalid")

    def _scan_unicode_escape(self) -> int:
        start = self.index + 1
        end = start + 4
        token = self.text[start:end]
        if len(token) != 4 or any(
            value not in "0123456789abcdefABCDEF" for value in token
        ):
            raise JsonPreflightError("invalid")
        self.index = end
        return int(token, 16)

    def _scan_number(self) -> None:
        start = self.index
        self._consume_if("-")
        if self.index >= len(self.text):
            raise JsonPreflightError("invalid")
        if self.text[self.index] == "0":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index].isdigit():
                raise JsonPreflightError("invalid")
        elif self.text[self.index] in "123456789":
            self.index += 1
            while self.index < len(self.text) and self.text[self.index].isdigit():
                self.index += 1
        else:
            raise JsonPreflightError("invalid")
        if self._consume_if("."):
            fraction_start = self.index
            while self.index < len(self.text) and self.text[self.index].isdigit():
                self.index += 1
            if self.index == fraction_start:
                raise JsonPreflightError("invalid")
        if self.index < len(self.text) and self.text[self.index] in "eE":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index] in "+-":
                self.index += 1
            exponent_start = self.index
            while self.index < len(self.text) and self.text[self.index].isdigit():
                self.index += 1
            if self.index == exponent_start:
                raise JsonPreflightError("invalid")
        if (
            self.maximum_number_characters is not None
            and self.index - start > self.maximum_number_characters
        ):
            raise JsonPreflightError("scalar")

    def _count_node(self) -> None:
        self.nodes += 1
        if self.nodes > self.maximum_nodes:
            raise JsonPreflightError("nodes")

    def _skip_whitespace(self) -> None:
        while self.index < len(self.text) and self.text[self.index] in " \t\r\n":
            self.index += 1

    def _consume_if(self, marker: str) -> bool:
        if self.index < len(self.text) and self.text[self.index] == marker:
            self.index += 1
            return True
        return False


def _json_code_point_bytes(code_point: int) -> int:
    if code_point <= 0x7F:
        return 1
    if code_point <= 0x7FF:
        return 2
    if code_point <= 0xFFFF:
        return 3
    return 4
