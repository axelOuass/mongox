"""Backing collections up to .mongo files and restoring them. Progress goes
to the `report` callback."""

import os
import tempfile

import mongo_file_formatter
from document_formatter import human
from errors import MongoxError

BATCH_BYTES = 16 * 1024 * 1024
BATCH_DOCS = 1000

# What to do with collections that already hold documents.
SKIP, DROP, APPEND = "skip", "drop", "append"


def backup(source, db_name, coll_names, out_path, compresslevel=6, report=None):
    """Writes the collections to one .mongo file. Returns the header written."""
    report = report or (lambda text: None)

    spool = tempfile.TemporaryFile(dir=os.path.dirname(os.path.abspath(out_path)))
    entries = []
    try:
        for coll_name in coll_names:
            options, kind, indexes = source.metadata(db_name, coll_name)
            if kind != "collection":
                report("  skipping %-28s (%s, not a collection)" % (coll_name, kind))
                continue

            count = written = 0
            for raw in source.raw_documents(db_name, coll_name):
                spool.write(raw)
                written += len(raw)
                count += 1

            entries.append({"name": coll_name, "count": count, "bytes": written,
                            "options": options, "indexes": indexes})
            report("  %-30s %8d docs  %10s  %d indexes"
                   % (coll_name, count, human(written), len(indexes)))

        if not entries:
            raise MongoxError("nothing to write: no real collections in that set")

        header = mongo_file_formatter.new_header(db_name, entries)
        mongo_file_formatter.write_file(out_path, header, spool, compresslevel)
    except BaseException:
        if os.path.exists(out_path):
            os.unlink(out_path)
        raise
    finally:
        spool.close()

    total_docs = sum(entry["count"] for entry in entries)
    total_raw = sum(entry["bytes"] for entry in entries)
    on_disk = os.path.getsize(out_path)
    report("Wrote %s  (%d docs, %s raw -> %s, %.0f%%)"
           % (out_path, total_docs, human(total_raw), human(on_disk),
              100.0 * on_disk / total_raw if total_raw else 0))
    return header


def read_header(path):
    stream, header = mongo_file_formatter.open_file(path)
    stream.close()
    return header


def clashes(source, header, into_db, rename=None):
    """Collections in the destination that already hold documents."""
    rename = rename or {}
    existing = set(source.collections(into_db))
    found = []
    for entry in header["collections"]:
        name = rename.get(entry["name"], entry["name"])
        if name in existing and source.count(into_db, name) > 0:
            found.append(name)
    return found


def restore(source, path, into=None, only=None, mode=SKIP, rename=None,
            report=None):
    """Restores a .mongo file into a database. Returns the documents inserted.
    With SKIP, any clash refuses the whole restore."""
    report = report or (lambda text: None)
    rename = rename or {}
    stream, header = mongo_file_formatter.open_file(path)
    db_name = into or header["database"]
    entries = header["collections"]

    if only:
        entries = [entry for entry in entries if entry["name"] in only]
        missing = set(only) - {entry["name"] for entry in entries}
        if missing:
            raise MongoxError("blob has no collection(s): %s"
                              % ", ".join(sorted(missing)))

    existing = set(source.collections(db_name))

    if mode == SKIP:
        found = clashes(source, {"collections": entries}, db_name, rename)
        if found:
            raise MongoxError(
                "these collections already hold documents in %s: %s"
                % (db_name, ", ".join(found)))

    report("Restoring into %s (from %s, taken %s)"
           % (db_name, header["database"], header.get("created", "?")))

    wanted = {entry["name"] for entry in entries}
    total = 0
    for entry in header["collections"]:
        stored = entry["name"]
        if stored not in wanted:
            mongo_file_formatter.skip_bytes(stream, entry["bytes"], stored)
            continue

        name = rename.get(stored, stored)
        if mode == DROP and name in existing:
            source.drop_collection(db_name, name)
            existing.discard(name)
        if name not in existing and entry.get("options"):
            source.create_collection(db_name, name, entry["options"])

        batch, batch_bytes, inserted = [], 0, 0
        for raw in mongo_file_formatter.iter_raw_documents(stream, entry["count"]):
            batch.append(raw)
            batch_bytes += len(raw)
            if len(batch) >= BATCH_DOCS or batch_bytes >= BATCH_BYTES:
                insert(source, db_name, name, batch)
                inserted += len(batch)
                batch, batch_bytes = [], 0
        if batch:
            insert(source, db_name, name, batch)
            inserted += len(batch)

        made = create_indexes(source, db_name, name, entry.get("indexes", []),
                              report)
        label = name if name == stored else "%s -> %s" % (stored, name)
        report("  %-30s %8d docs  %d indexes" % (label, inserted, made))
        total += inserted

    stream.close()
    return total


def insert(source, db_name, coll_name, raw_batch):
    try:
        source.insert_raw(db_name, coll_name, raw_batch)
    except MongoxError:
        raise
    except Exception as error:
        raise MongoxError("insert into %s.%s failed: %s"
                          % (db_name, coll_name, error))


def create_indexes(source, db_name, coll_name, indexes, report):
    """An index that fails is reported and skipped. The documents are already in."""
    specs = [dict(spec) for spec in indexes if spec.get("name") != "_id_"]
    if not specs:
        return 0
    try:
        return source.create_indexes(db_name, coll_name, specs)
    except Exception as error:
        report("  ! index creation failed on %s: %s" % (coll_name, error))
        return 0
