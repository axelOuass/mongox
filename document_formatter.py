"""Labels, counts and sizes as text."""

# Fields a row label is taken from, in order. The list pane fetches only these.
SUMMARY_FIELDS = ("name", "reference", "company", "title", "email", "duty")


def summarise(document):
    """A one-line label for a document."""
    for key in SUMMARY_FIELDS + ("_id",):
        value = document.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return str(value)
    return str(document.get("_id", "?"))


def plural(number, thing):
    return "%d %s%s" % (number, thing, "" if number == 1 else "s")


def human(nbytes):
    value = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return "%.0f %s" % (value, unit) if unit == "B" else "%.1f %s" % (value, unit)
        value /= 1024


def json_array(source, documents):
    return "[\n%s\n]" % ",\n".join(source.to_json(document)
                                    for document in documents)
