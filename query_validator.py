"""Turns what the user typed in a search into a Mongo query."""

import re

from errors import MongoxError


def collect_fields(documents, max_depth=2, sample=200):
    """Field names in a sample of documents, nested ones dotted. Mongo queries
    dotted paths natively, so 'hazard.class' works as a field."""
    fields, seen = [], set()

    def walk(document, prefix, depth):
        if not isinstance(document, dict):
            return
        for key, value in document.items():
            path = prefix + key
            if path not in seen:
                seen.add(path)
                fields.append(path)
            if depth < max_depth and isinstance(value, dict):
                walk(value, path + ".", depth + 1)

    for document in documents[:sample]:
        walk(document, "", 1)
    return fields


def coerce(text):
    """'45' -> 45, 'true' -> True, anything else stays a string."""
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    for converter in (int, float):
        try:
            return converter(stripped)
        except ValueError:
            pass
    return text


def build_field_query(field, value):
    """A query for one field. A '*' anywhere makes it a wildcard search.

        harry           exactly "harry"
        harry*          starts with
        *harry          ends with
        *harry*         contains
        *har*y*         both, in order

    Wildcard searches are case-insensitive, exact ones are not.
    """
    if "*" not in value:
        typed = coerce(value)
        if typed == value:
            return {field: value}
        # The value may be stored as a number or as a string. Both are matched.
        return {field: {"$in": [typed, value]}}

    pattern = ".*".join(re.escape(part) for part in value.split("*"))
    if not value.startswith("*"):
        pattern = "^" + pattern
    if not value.endswith("*"):
        pattern = pattern + "$"
    return {field: {"$regex": pattern, "$options": "i"}}


def parse_raw_query(source, text):
    try:
        query = source.from_json(text)
    except Exception as error:
        raise MongoxError("bad query: %s" % error)
    if not isinstance(query, dict):
        raise MongoxError("a query has to be a JSON object")
    return query
