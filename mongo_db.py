"""The live server. The only module that talks to pymongo."""

from credentials import redact
from document_formatter import SUMMARY_FIELDS
from errors import MongoxError

SYSTEM_DBS = {"admin", "local", "config"}
DOC_LIMIT = 500


class MongoDb:
    def __init__(self, uri):
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
        except PyMongoError as error:
            raise MongoxError("could not connect: %s" % error)
        self.uri = uri
        self.label = redact(uri)

    def databases(self):
        return sorted(name for name in self.client.list_database_names()
                      if name not in SYSTEM_DBS)

    def collections(self, db):
        if not db:
            return []
        return sorted(name for name in self.client[db].list_collection_names()
                      if not name.startswith("system."))

    def count(self, db, coll):
        return self.client[db][coll].estimated_document_count()

    def documents(self, db, coll, query=None, limit=DOC_LIMIT):
        if not (db and coll):
            return []
        return list(self.client[db][coll].find(query or {}).limit(limit))

    def summaries(self, db, coll, query=None, limit=DOC_LIMIT):
        """Only the fields a row label needs, so large documents cost the same
        as small ones."""
        if not (db and coll):
            return []
        projection = {field: 1 for field in SUMMARY_FIELDS}
        return list(self.client[db][coll].find(query or {}, projection)
                    .limit(limit))

    def document(self, db, coll, doc_id):
        return self.client[db][coll].find_one({"_id": doc_id})

    def raw_documents(self, db, coll):
        """Undecoded BSON, for the .mongo writer."""
        from bson.raw_bson import RawBSONDocument
        from bson.codec_options import CodecOptions
        codec = CodecOptions(document_class=RawBSONDocument)
        collection = self.client[db].get_collection(coll, codec_options=codec)
        for document in collection.find({}, batch_size=1000):
            yield document.raw

    def metadata(self, db, coll):
        """Returns (options, kind, indexes). The automatic _id_ index is left
        out, because restore never recreates it."""
        options, kind = {}, "collection"
        for entry in self.client[db].list_collections(filter={"name": coll}):
            options = entry.get("options", {}) or {}
            kind = entry.get("type", "collection")
        indexes = []
        for spec in self.client[db][coll].list_indexes():
            spec = dict(spec)
            if spec.get("name") == "_id_":
                continue
            spec.pop("v", None)
            spec.pop("ns", None)
            indexes.append(spec)
        return options, kind, indexes

    def replace(self, db, coll, doc_id, document):
        self.client[db][coll].replace_one({"_id": doc_id}, document)

    def delete(self, db, coll, doc_id):
        self.client[db][coll].delete_one({"_id": doc_id})

    def drop_collection(self, db, coll):
        self.client[db].drop_collection(coll)

    def drop_database(self, db):
        self.client.drop_database(db)

    def create_collection(self, db, coll, options=None):
        self.client[db].create_collection(coll, **(options or {}))

    def insert_raw(self, db, coll, raw_documents):
        """Inserts undecoded BSON, so every type stays exactly as stored."""
        from bson.raw_bson import RawBSONDocument
        self.client[db][coll].insert_many(
            [RawBSONDocument(raw) for raw in raw_documents], ordered=False)

    def insert_one(self, db, coll, document):
        self.client[db][coll].insert_one(document)

    def create_indexes(self, db, coll, specs):
        if not specs:
            return 0
        self.client[db].command("createIndexes", coll, indexes=specs)
        return len(specs)

    def to_json(self, document):
        from bson import json_util
        return json_util.dumps(document, indent=2, ensure_ascii=False)

    def from_json(self, text):
        from bson import json_util
        return json_util.loads(text)
