"""
Copy and paste at three levels: document, collection, database.

The clipboard holds data, not a reference, so a collection copied off a VPS
survives the tunnel closing and can be pasted into localhost afterwards.
Anything bigger than a single document spools to a temporary .mongo file.
"""

import os
import tempfile

import backup_manager
from backup_manager import SKIP
from document_formatter import summarise
from errors import MongoxError

DOCUMENT, COLLECTION, DATABASE = "document", "collection", "database"
# The plural kinds hold a selection made with space in the browser.
DOCUMENTS, COLLECTIONS = "documents", "collections"

# How a pasted document treats its _id.
KEEP_ID, NEW_ID, REPLACE = "keep", "new", "replace"


class Clipboard:
    def __init__(self):
        self.kind = None
        self.origin = ""        # where it came from, for display
        self.db_name = None
        self.coll_name = None
        self.document = None    # DOCUMENT only
        self.documents = []     # DOCUMENTS only
        self.path = None        # COLLECTION, COLLECTIONS and DATABASE: a .mongo file
        self.header = None
        self.count = 0

    @property
    def full(self):
        return self.kind is not None

    def describe(self):
        if not self.full:
            return ""
        if self.kind == DOCUMENT:
            return "document %s" % summarise(self.document)
        if self.kind == DOCUMENTS:
            return "%d documents" % self.count
        if self.kind == COLLECTION:
            return "%s (%d docs)" % (self.coll_name, self.count)
        if self.kind == COLLECTIONS:
            return "%d collections (%d docs)" % (
                len(self.header["collections"]), self.count)
        return "%s (%d collections, %d docs)" % (
            self.db_name, len(self.header["collections"]), self.count)

    def clear(self):
        if self.path and os.path.exists(self.path):
            try:
                os.unlink(self.path)
            except OSError:
                pass
        self.__init__()

    def default_name(self):
        return self.coll_name if self.kind == COLLECTION else self.db_name

    def copy_document(self, source, db_name, coll_name, document):
        self.clear()
        self.kind = DOCUMENT
        self.origin = "%s  %s.%s" % (source.label, db_name, coll_name)
        self.db_name, self.coll_name = db_name, coll_name
        self.document = document
        self.count = 1

    def copy_documents(self, source, db_name, coll_name, documents):
        self.clear()
        self.kind = DOCUMENTS
        self.origin = "%s  %s.%s" % (source.label, db_name, coll_name)
        self.db_name, self.coll_name = db_name, coll_name
        self.documents = list(documents)
        self.count = len(self.documents)

    def copy_collections(self, source, db_name, coll_names, report=None):
        self._spool(source, db_name, list(coll_names), report)
        self.kind = COLLECTIONS
        self.coll_name = None

    def copy_collection(self, source, db_name, coll_name, report=None):
        self._spool(source, db_name, [coll_name], report)
        self.kind = COLLECTION
        self.coll_name = coll_name

    def copy_database(self, source, db_name, report=None):
        names = source.collections(db_name)
        if not names:
            raise MongoxError("%s has no collections to copy" % db_name)
        self._spool(source, db_name, names, report)
        self.kind = DATABASE
        self.coll_name = None

    def _spool(self, source, db_name, coll_names, report):
        self.clear()
        handle, path = tempfile.mkstemp(prefix="mongox-clip-", suffix=".mongo")
        os.close(handle)
        try:
            self.header = backup_manager.backup(source, db_name, coll_names, path,
                                                compresslevel=1, report=report)
        except BaseException:
            if os.path.exists(path):
                os.unlink(path)
            raise
        self.path = path
        self.origin = "%s  %s" % (source.label, db_name)
        self.db_name = db_name
        self.count = sum(entry["count"] for entry in self.header["collections"])

    def paste_document(self, source, db_name, coll_name, mode=NEW_ID):
        return paste_one(source, db_name, coll_name, self.document, mode)

    def paste_documents(self, source, db_name, coll_name, mode=NEW_ID):
        """Returns how many went in."""
        for document in self.documents:
            paste_one(source, db_name, coll_name, document, mode)
        return len(self.documents)

    def paste_blob(self, source, into_db, rename=None, mode=SKIP, report=None):
        """COLLECTION, COLLECTIONS or DATABASE into `into_db`. `rename` maps
        the stored collection name to a new one."""
        if not self.path or not os.path.exists(self.path):
            raise MongoxError("the clipboard is empty or its spool file is gone")
        return backup_manager.restore(source, self.path, into=into_db,
                                      rename=rename, mode=mode, report=report)

    def would_clash(self, source, into_db, rename=None):
        return backup_manager.clashes(source, self.header, into_db, rename)


def paste_one(source, db_name, coll_name, document, mode):
    """NEW_ID gives it a fresh _id, KEEP_ID fails on a clash, REPLACE
    overwrites the document already using that _id."""
    document = dict(document)

    if mode == NEW_ID:
        document.pop("_id", None)
        try:
            from bson import ObjectId
            document["_id"] = ObjectId()
        except ImportError:
            pass
        source.insert_one(db_name, coll_name, document)
        return document.get("_id")

    existing = source.documents(db_name, coll_name,
                                {"_id": document.get("_id")}, limit=1)
    if existing:
        if mode != REPLACE:
            raise MongoxError(
                "a document with that _id is already in %s.%s"
                % (db_name, coll_name))
        source.replace(db_name, coll_name, document["_id"], document)
        return document.get("_id")

    source.insert_one(db_name, coll_name, document)
    return document.get("_id")
