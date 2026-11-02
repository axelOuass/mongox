"""
The .mongo single-file format.

    MAGIC (8 bytes, plain)  +  gzip stream of:
        uint32 little-endian header length
        header  (extended JSON: db name, collections, counts, indexes, options)
        raw BSON documents, concatenated, in header order

Documents are copied as raw bytes and never decoded, so ObjectIds, dates,
Decimal128 and binary fields come back as they were. The document region is
byte-identical to what mongodump puts in its .bson files.
"""

import gzip
import shutil
import struct
from datetime import datetime, timezone

from errors import MongoxError

MAGIC = b"MONGOX\x01\x00"
FORMAT_VERSION = 1


def new_header(db_name, entries):
    return {"format": FORMAT_VERSION, "tool": "mongox",
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "database": db_name, "collections": entries}


def open_file(path):
    """Returns (stream, header) with the stream at the first document."""
    from bson import json_util

    try:
        raw = open(path, "rb")
    except OSError as error:
        raise MongoxError(str(error))

    if raw.read(len(MAGIC)) != MAGIC:
        raw.close()
        raise MongoxError("%s is not a mongox file (bad magic)" % path)

    stream = gzip.GzipFile(fileobj=raw, mode="rb")
    length_bytes = stream.read(4)
    if len(length_bytes) != 4:
        raise MongoxError("%s is truncated" % path)
    (header_length,) = struct.unpack("<I", length_bytes)
    header = json_util.loads(stream.read(header_length).decode("utf-8"))

    if header.get("format") != FORMAT_VERSION:
        raise MongoxError("unsupported format version %r in %s"
                          % (header.get("format"), path))
    return stream, header


def write_file(path, header, spool, compresslevel=6):
    from bson import json_util

    header_bytes = json_util.dumps(header).encode("utf-8")
    spool.seek(0)
    with open(path, "wb") as raw:
        raw.write(MAGIC)
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=compresslevel) as gz:
            gz.write(struct.pack("<I", len(header_bytes)))
            gz.write(header_bytes)
            shutil.copyfileobj(spool, gz, 1 << 20)


def iter_raw_documents(stream, count):
    """Yields `count` raw BSON documents. Each starts with its own length."""
    for index in range(count):
        size_bytes = stream.read(4)
        if len(size_bytes) != 4:
            raise MongoxError("blob truncated at document %d of %d"
                              % (index + 1, count))
        (size,) = struct.unpack("<i", size_bytes)
        if size < 5:
            raise MongoxError("corrupt document length (%d) at document %d"
                              % (size, index + 1))
        body = stream.read(size - 4)
        if len(body) != size - 4:
            raise MongoxError("blob truncated inside document %d" % (index + 1))
        yield size_bytes + body


def skip_bytes(stream, nbytes, name):
    while nbytes > 0:
        chunk = stream.read(min(nbytes, 1 << 20))
        if not chunk:
            raise MongoxError("blob truncated while skipping %s" % name)
        nbytes -= len(chunk)
