"""Bounded JSON Schema subset shared by authored and runtime eval validation."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import islice
import math
from typing import TypeAlias

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable


MAX_JSON_SCHEMA_BYTES = 256 * 1024
MAX_JSON_SCHEMA_NODES = 512
MAX_JSON_SCHEMA_DEPTH = 32
MAX_JSON_SCHEMA_REFERENCES = 128
MAX_JSON_SCHEMA_VALIDATION_ERRORS = 64

# Regex execution is intentionally outside the runner schema contract.
REGEX_SCHEMA_KEYWORDS = frozenset(("pattern", "patternProperties"))

# Branching and conditional validation can multiply work across the instance.
COMBINATOR_CONDITIONAL_SCHEMA_KEYWORDS = frozenset(
    ("allOf", "anyOf", "else", "if", "not", "oneOf", "then")
)

# These advanced keywords are unnecessary for the intentionally small runner subset.
UNSUPPORTED_ADVANCED_SCHEMA_KEYWORDS = frozenset(
    (
        "$dynamicRef",
        "contains",
        "dependentRequired",
        "dependentSchemas",
        "maxContains",
        "minContains",
        "prefixItems",
        "propertyNames",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
    )
)

REJECTED_SCHEMA_KEYWORDS = (
    REGEX_SCHEMA_KEYWORDS
    | COMBINATOR_CONDITIONAL_SCHEMA_KEYWORDS
    | UNSUPPORTED_ADVANCED_SCHEMA_KEYWORDS
)

ALLOWED_SCHEMA_KEYWORDS = frozenset(
    (
        "$defs",
        "$ref",
        "$schema",
        "additionalProperties",
        "const",
        "description",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "items",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "properties",
        "required",
        "title",
        "type",
    )
)


SchemaPath: TypeAlias = tuple[str, ...]
SchemaNode: TypeAlias = Mapping[str, object] | bool


class JsonSchemaPolicyError(ValueError):
    """A runner schema is invalid or outside the bounded supported subset."""


def build_safe_json_schema_validator(
    document: object,
) -> Draft202012Validator:
    """Validate the bounded subset and return a closed-reference validator."""
    if not isinstance(document, Mapping):
        raise JsonSchemaPolicyError("JSON Schema root must be an object")
    _validate_json_document_limits(document)

    nodes: dict[SchemaPath, SchemaNode] = {}
    edges: dict[SchemaPath, set[SchemaPath]] = {}
    references: list[tuple[SchemaPath, str]] = []
    _collect_schema_graph(document, (), nodes, edges, references)
    if len(references) > MAX_JSON_SCHEMA_REFERENCES:
        raise JsonSchemaPolicyError("JSON Schema exceeds the reference limit")
    for source, reference in references:
        target = _local_reference_path(reference)
        if target not in nodes:
            raise JsonSchemaPolicyError("JSON Schema contains an unresolved local reference")
        edges[source].add(target)
    _reject_reference_cycles(edges)

    try:
        Draft202012Validator.check_schema(document)
        return Draft202012Validator(document, registry=Registry())
    except SchemaError as error:
        raise JsonSchemaPolicyError("JSON Schema is invalid") from error


def bounded_json_schema_errors(
    validator: Draft202012Validator,
    instance: object,
) -> tuple[ValidationError, ...]:
    """Materialize no more than the shared validation-error limit."""
    try:
        return tuple(
            islice(
                validator.iter_errors(instance),
                MAX_JSON_SCHEMA_VALIDATION_ERRORS,
            )
        )
    except (RecursionError, Unresolvable) as error:
        raise JsonSchemaPolicyError("safe JSON Schema validation failed closed") from error


def _validate_json_document_limits(document: object) -> None:
    nodes = 0
    pending: list[tuple[object, int]] = [(document, 1)]
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_SCHEMA_NODES:
            raise JsonSchemaPolicyError("JSON Schema exceeds the node limit")
        if depth > MAX_JSON_SCHEMA_DEPTH:
            raise JsonSchemaPolicyError("JSON Schema exceeds the depth limit")
        if isinstance(value, Mapping):
            if not all(isinstance(key, str) for key in value):
                raise JsonSchemaPolicyError("JSON Schema object keys must be strings")
            pending.extend((nested, depth + 1) for nested in value.values())
        elif isinstance(value, list):
            pending.extend((nested, depth + 1) for nested in value)
        elif value is None or isinstance(value, (bool, int, str)):
            continue
        elif isinstance(value, float) and math.isfinite(value):
            continue
        else:
            raise JsonSchemaPolicyError("JSON Schema must contain only JSON values")


def _collect_schema_graph(
    schema: SchemaNode,
    path: SchemaPath,
    nodes: dict[SchemaPath, SchemaNode],
    edges: dict[SchemaPath, set[SchemaPath]],
    references: list[tuple[SchemaPath, str]],
) -> None:
    nodes[path] = schema
    edges[path] = set()
    if isinstance(schema, bool):
        return

    for keyword in schema:
        if keyword in REJECTED_SCHEMA_KEYWORDS:
            raise JsonSchemaPolicyError(
                f"JSON Schema keyword '{keyword}' is not allowed by the safe subset"
            )
        if keyword not in ALLOWED_SCHEMA_KEYWORDS:
            raise JsonSchemaPolicyError(
                f"unsupported JSON Schema keyword '{keyword}'"
            )

    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str):
            raise JsonSchemaPolicyError("JSON Schema reference must be a string")
        references.append((path, reference))

    for child_path, child_schema in _schema_children(schema, path):
        edges[path].add(child_path)
        _collect_schema_graph(child_schema, child_path, nodes, edges, references)


def _schema_children(
    schema: Mapping[str, object],
    path: SchemaPath,
) -> tuple[tuple[SchemaPath, SchemaNode], ...]:
    children: list[tuple[SchemaPath, SchemaNode]] = []
    for keyword in ("$defs", "properties"):
        declarations = schema.get(keyword)
        if not isinstance(declarations, Mapping):
            continue
        for name, child in declarations.items():
            if isinstance(name, str) and isinstance(child, (Mapping, bool)):
                children.append(((*path, keyword, name), child))
    for keyword in ("items", "additionalProperties"):
        child = schema.get(keyword)
        if isinstance(child, (Mapping, bool)):
            children.append(((*path, keyword), child))
    return tuple(children)


def _local_reference_path(reference: str) -> SchemaPath:
    if not reference.startswith("#"):
        raise JsonSchemaPolicyError(
            "external JSON Schema reference is not allowed (unresolved reference)"
        )
    if reference == "#":
        return ()
    if not reference.startswith("#/") or "%" in reference:
        raise JsonSchemaPolicyError(
            "JSON Schema reference must use a local JSON Pointer fragment"
        )
    tokens: list[str] = []
    for raw_token in reference[2:].split("/"):
        if _has_invalid_json_pointer_escape(raw_token):
            raise JsonSchemaPolicyError("JSON Schema reference has an invalid JSON Pointer")
        tokens.append(raw_token.replace("~1", "/").replace("~0", "~"))
    return tuple(tokens)


def _has_invalid_json_pointer_escape(token: str) -> bool:
    index = 0
    while index < len(token):
        if token[index] == "~":
            if index + 1 >= len(token) or token[index + 1] not in "01":
                return True
            index += 2
        else:
            index += 1
    return False


def _reject_reference_cycles(edges: Mapping[SchemaPath, set[SchemaPath]]) -> None:
    states: dict[SchemaPath, int] = {}

    def visit(path: SchemaPath) -> None:
        state = states.get(path, 0)
        if state == 1:
            raise JsonSchemaPolicyError(
                "JSON Schema contains a recursive local reference cycle"
            )
        if state == 2:
            return
        states[path] = 1
        for target in edges[path]:
            visit(target)
        states[path] = 2

    for path in edges:
        visit(path)
