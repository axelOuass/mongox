"""Editing and deleting documents, collections and databases. The browser asks
the user, this module decides and writes."""

from errors import MongoxError


class NotJson(MongoxError):
    pass


class IdChanged(MongoxError):
    pass


def parse_edit(source, original, before, after):
    """The edited document, or None when the text is unchanged."""
    if after.strip() == before.strip():
        return None
    try:
        updated = source.from_json(after)
    except Exception as error:
        raise NotJson(str(error))
    if updated.get("_id") != original.get("_id"):
        raise IdChanged("_id changed - refusing to save")
    return updated


def save(source, db, coll, original, updated):
    try:
        source.replace(db, coll, original["_id"], updated)
    except Exception as error:
        raise MongoxError("save failed: %s" % error)


def whole_documents(source, db, coll, rows):
    """The whole documents behind list summaries, in one round trip and in the
    order given."""
    if not rows:
        return []
    wanted = [row["_id"] for row in rows]
    found = source.documents(db, coll, {"_id": {"$in": wanted}}, limit=len(wanted))
    by_id = {document["_id"]: document for document in found}
    return [by_id.get(key, row) for key, row in zip(wanted, rows)]


def collection_counts(source, db, names=None):
    """(name, count) for the named collections, or for all of them."""
    if names is None:
        names = source.collections(db)
    return [(name, source.count(db, name)) for name in names]


def delete_documents(source, db, coll, documents):
    done = 0
    try:
        for document in documents:
            source.delete(db, coll, document["_id"])
            done += 1
    except Exception as error:
        raise MongoxError("deleted %d, then failed: %s" % (done, error))
    return done


def drop_collections(source, db, names, report=None):
    report = report or (lambda text: None)
    done = 0
    try:
        for name in names:
            report("Dropping %s ..." % name)
            source.drop_collection(db, name)
            done += 1
    except Exception as error:
        raise MongoxError("dropped %d, then failed: %s" % (done, error))
    return done


def drop_database(source, db):
    try:
        source.drop_database(db)
    except Exception as error:
        raise MongoxError("drop failed: %s" % error)
