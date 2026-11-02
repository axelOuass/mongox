"""
The three-pane browser: databases, collections, documents, with the selected
document below.

Asks the user, then hands the decision to the managers.
"""

import curses
import os

import backup_manager
import clipboard_manager
import document_manager
import query_validator
from clipboard_manager import Clipboard
from document_formatter import human, json_array, plural, summarise
from errors import MongoxError
from ui import files, sysclip, theme, widgets
from ui.editor import edit_text_externally
from ui.theme import DANGER, DIM, FRAME, KEY, OK, TITLE, attr
from ui.widgets import ListPane, StatusBar, TextPane, put

KEYS = [("↑↓←→", "move"), ("space", "select"), ("e", "edit"), ("d", "delete"),
        ("y", "copy"), ("p", "paste"), ("J", "json"), ("b", "backup"),
        ("i", "import"), ("/", "search"), ("c", "connections"), ("q", "quit")]

# Keys shown while selecting. Paste is not one of them.
SELECT_KEYS = [("↑↓", "move"), ("space", "pick"), ("y", "copy"), ("J", "json"),
               ("b", "backup"), ("d", "delete"), ("esc", "cancel")]

# Past this size clipboard managers and compositors struggle, so the copy
# is confirmed first.
CLIP_WARN_BYTES = 10 * 1024 * 1024

HELP = """  ↑ ↓  or  j k        move within a pane
  ← →  or  h l  tab   move between panes
  g / G               first / last
  PgUp / PgDn         scroll the document below

  space               enter selection mode, in the collections or the
                      documents pane, with the row under the cursor picked.
                      space picks and unpicks; the panes are locked while
                      selecting, so a selection cannot be left somewhere out
                      of sight. y, J, b and d act on the whole selection and
                      then leave the mode, and esc leaves without acting.
                      There is no paste while selecting: a selection is
                      something to act on, not somewhere to put things.

  e                   edit the selected document in $EDITOR
  d                   delete: the documents picked or the one under the
                      cursor, a collection from the collections pane, or a
                      whole database from the databases pane. Always asks
                      first, and says what is about to go.

  y                   copy: a document, a collection, or a whole database,
                      depending on which pane you are in
  p                   paste whatever was copied, here
  J                   copy JSON to the system clipboard: the selected
                      document, or every document shown in the collection

  b                   back up to a .mongo file: the collection you are on,
                      or the whole database from the databases pane
  i                   import a .mongo file back into a database

  /                   search: pick a field and type a value, or raw JSON
  r                   reload from the server
  w                   unlock writes on a read-only connection
  c                   back to the connection list
  q                   quit"""

SWITCH = "switch"          # the browser asks to go back to the connection list

# How many whole documents to read when working out what fields a collection
# has. The list itself holds summaries, which do not carry enough to go on.
FIELD_SAMPLE = 50
MIN_WIDTH, MIN_HEIGHT = 72, 16


class Browser:
    DB, COLL, DOC = 0, 1, 2

    def __init__(self, source, read_only=False, clip=None):
        self.source = source
        self.read_only = read_only
        self.clip = clip if clip is not None else Clipboard()
        self.query = None
        self.query_label = ""
        self.documents = []
        self.outcome = None
        self.selecting = False
        self.full = {}          # row position -> whole document, once fetched

        self.panes = [ListPane("databases"), ListPane("collections"),
                      ListPane("documents")]
        self.preview = TextPane("document")
        self.status = StatusBar(KEYS)
        self.focus = self.DB
        self.load_databases()


    @property
    def pane(self):
        return self.panes[self.focus]

    def _label(self, index):
        pane = self.panes[index]
        return pane.rows[pane.index][0].strip() if pane.rows else None

    @property
    def current_db(self):
        return self._label(self.DB)

    @property
    def current_coll(self):
        return self._label(self.COLL)

    @property
    def current_doc(self):
        """The whole document under the cursor, fetched the first time its row
        is looked at and kept while the list stands."""
        pane = self.panes[self.DOC]
        if not self.documents:
            return None
        position = pane.index
        if position in self.full:
            return self.full[position]

        summary = self.documents[position]
        try:
            document = self.source.document(self.current_db, self.current_coll,
                                            summary["_id"])
        except Exception:
            document = None
        self.full[position] = document or summary
        return self.full[position]

    def load_databases(self, keep=False):
        names = self.source.databases()
        self.panes[self.DB].set_rows([(name, "") for name in names], keep)
        self.load_collections(keep)

    def load_collections(self, keep=False):
        db = self.current_db
        names = self.source.collections(db) if db else []
        rows = [(name, str(self.source.count(db, name))) for name in names]
        self.panes[self.COLL].set_rows(rows, keep)
        self.load_documents(keep)

    def load_documents(self, keep=False):
        db, coll = self.current_db, self.current_coll
        self.full = {}
        self.documents = self.source.summaries(db, coll, self.query) \
            if (db and coll) else []
        self.panes[self.DOC].set_rows(
            [(summarise(document), "") for document in self.documents], keep)
        self.refresh_preview()

    def refresh_preview(self):
        document = self.current_doc
        if document is None:
            self.preview.set_rows([[("no document selected", DIM, False)]])
            self.preview.subtitle = ""
            return
        self.preview.set_rows(widgets.tokenize_json(self.source.to_json(document)))
        self.preview.subtitle = "%d/%d" % (self.panes[self.DOC].index + 1,
                                           len(self.documents))

    def draw(self, window):
        window.erase()
        height, width = window.getmaxyx()
        if height < MIN_HEIGHT or width < MIN_WIDTH:
            put(window, 0, 0, "terminal too small (need %dx%d)"
                % (MIN_WIDTH, MIN_HEIGHT), attr(DANGER, True))
            window.refresh()
            return

        self.draw_header(window, width)

        top = 4
        pane_height = max(7, (height - top - 3) * 3 // 5)
        third = width // 3
        widths = [third, third, width - 2 * third]
        counts = ["%d" % len(self.panes[self.DB].rows),
                  "%d" % len(self.panes[self.COLL].rows),
                  "%d shown" % len(self.documents)]
        for index, pane in enumerate(self.panes):
            if pane.marked:
                counts[index] = "%d of %s selected" % (len(pane.marked),
                                                       counts[index].split()[0])

        left = 0
        for index, pane in enumerate(self.panes):
            pane.active = index == self.focus
            pane.subtitle = counts[index]
            pane.place(top, left, pane_height, widths[index])
            pane.draw(window)
            left += widths[index]

        preview_height = height - (top + pane_height) - 2
        if preview_height >= 4:
            self.preview.active = self.focus == self.DOC
            self.preview.place(top + pane_height, 0, preview_height, width)
            self.preview.draw(window)

        self.status.draw(window, height - 1, width)
        window.refresh()

    def draw_header(self, window, width):
        put(window, 0, 0, "─" * width, attr(FRAME))
        put(window, 1, 2, "mongo", attr(OK, True))
        put(window, 1, 7, "X", attr(TITLE, True))
        put(window, 1, 9, "│", attr(FRAME))
        put(window, 1, 11, self.source.label, attr(DIM))

        badge = " READ-ONLY " if self.read_only else " WRITE "
        put(window, 1, width - len(badge) - 2, badge,
            attr(DANGER if self.read_only else OK, True))

        if self.clip.full:
            held = "clip: %s" % self.clip.describe()
            if len(held) < width - len(badge) - 6:
                put(window, 1, width - len(badge) - len(held) - 4, held,
                    attr(TITLE, True))

        trail = "%s / %s / %s" % (self.current_db or "-", self.current_coll or "-",
                                  summarise(self.current_doc) if self.current_doc
                                  else "-")
        put(window, 2, 2, trail, attr(KEY))
        if self.query:
            note = "search: %s" % (self.query_label or self.query)
            put(window, 2, max(len(trail) + 4, width - len(note) - 3), note,
                attr(TITLE, True))
        put(window, 3, 0, "─" * width, attr(FRAME))

    def move(self, delta):
        if self.pane.move(delta):
            self.after_move()

    def jump(self, position):
        if self.pane.go(position):
            self.after_move()

    def after_move(self):
        # A search belongs to the collection it was typed for. Moving to
        # another database or collection clears it.
        if self.focus == self.DB:
            self.clear_query()
            self.load_collections()
        elif self.focus == self.COLL:
            self.clear_query()
            self.load_documents()
        else:
            self.refresh_preview()

    def clear_query(self):
        self.query, self.query_label = None, ""

    def begin_select(self, window):
        if self.focus == self.DB:
            return self.status.notify(
                "space selects collections and documents, not databases",
                DANGER)
        if not self.pane.rows:
            return self.status.notify("nothing here to select", DANGER)
        self.selecting = True
        self.status.keys = SELECT_KEYS
        theme.init(selecting=True)
        self.pane.toggle()
        self.status.notify("%d selected" % len(self.pane.marked), OK)

    def end_select(self):
        self.selecting = False
        self.status.keys = KEYS
        theme.init(selecting=False)
        for pane in self.panes:
            pane.clear_marks()

    def switch(self, delta):
        """Panes are locked while the one in focus holds a selection, so that
        a selection cannot be left behind somewhere out of sight."""
        if self.pane.marked:
            return self.status.notify(
                "%d selected here - esc clears it, or y J b d act on it"
                % len(self.pane.marked), DANGER)
        self.focus = max(self.DB, min(self.DOC, self.focus + delta))

    def marked_documents(self):
        pane = self.panes[self.DOC]
        rows = [self.documents[position] for position in sorted(pane.marked)
                if position < len(self.documents)]
        return self.whole(rows)

    def whole(self, rows):
        return document_manager.whole_documents(self.source, self.current_db,
                                                self.current_coll, rows)

    def marked_collections(self):
        pane = self.panes[self.COLL]
        return [pane.rows[position][0].strip()
                for position in sorted(pane.marked) if position < len(pane.rows)]

    def writable(self):
        if self.read_only:
            self.status.notify("read-only session - press w to unlock writes",
                               DANGER)
            return False
        return True

    def edit(self, window):
        document = self.current_doc
        if not self.writable():
            return
        if document is None:
            return self.status.notify("nothing selected", DANGER)

        before = self.source.to_json(document)
        curses.endwin()
        after = edit_text_externally(before)
        window.clear()
        curses.doupdate()

        if after is None:
            return self.status.notify("no $EDITOR set and no fallback found",
                                      DANGER)
        try:
            updated = document_manager.parse_edit(self.source, document,
                                                  before, after)
        except document_manager.NotJson as error:
            return self.tell(window, "NOT SAVED",
                             "That is not valid JSON, so nothing was "
                             "written:\n\n%s" % error, danger=True)
        except document_manager.IdChanged as error:
            return self.status.notify(str(error), DANGER)
        if updated is None:
            return self.status.notify("unchanged")

        if not self.ask_yes(window, "Save changes to %s ?" % summarise(document)):
            return self.status.notify("not saved")
        try:
            document_manager.save(self.source, self.current_db, self.current_coll,
                                  document, updated)
        except MongoxError as error:
            return self.status.notify(str(error), DANGER)
        self.load_documents(keep=True)
        self.status.notify("saved", OK)

    def delete(self, window):
        """What is picked in the focused pane, or the row under the cursor:
        the same thing y copies from that pane."""
        if not self.writable():
            return
        if self.focus == self.DB:
            return self.delete_database(window)
        if self.focus == self.COLL:
            return self.delete_collections(window)
        return self.delete_documents(window)

    def delete_documents(self, window):
        chosen = self.marked_documents()
        if not chosen:
            if self.current_doc is None:
                return self.status.notify("nothing selected", DANGER)
            chosen = [self.current_doc]

        if len(chosen) == 1:
            question = "DELETE %s from %s.%s ?" % (
                summarise(chosen[0]), self.current_db, self.current_coll)
            body = None
        else:
            question = "DELETE %d documents from %s.%s ?" % (
                len(chosen), self.current_db, self.current_coll)
            body = ["  " + summarise(document) for document in chosen[:8]]
            if len(chosen) > 8:
                body.append("  ... and %d more" % (len(chosen) - 8))

        if not self.ask_yes(window, question, danger=True, body=body):
            return self.status.notify("not deleted")

        try:
            done = document_manager.delete_documents(
                self.source, self.current_db, self.current_coll, chosen)
        except MongoxError as error:
            self.load_collections(keep=True)
            return self.status.notify(str(error), DANGER)
        self.load_collections(keep=True)
        self.status.notify("deleted %d" % done if done > 1 else "deleted", OK)

    def delete_collections(self, window):
        db = self.current_db
        chosen = self.marked_collections()
        if not chosen:
            if not self.current_coll:
                return self.status.notify("nothing selected", DANGER)
            chosen = [self.current_coll]

        counts = document_manager.collection_counts(self.source, db, chosen)
        total = sum(count for _, count in counts)
        if len(chosen) == 1:
            question = "DROP %s.%s and its %s ?" % (
                db, chosen[0], plural(total, "document"))
            body = None
        else:
            question = "DROP %s from %s, %s in all ?" % (
                plural(len(chosen), "collection"), db,
                plural(total, "document"))
            body = ["  %s (%d)" % pair for pair in counts[:8]]
            if len(counts) > 8:
                body.append("  ... and %d more" % (len(counts) - 8))

        if not self.ask_yes(window, question, danger=True, body=body):
            return self.status.notify("not dropped")

        try:
            done = document_manager.drop_collections(
                self.source, db, chosen, report=lambda text: self.busy(window, text))
        except MongoxError as error:
            self.load_collections(keep=True)
            return self.status.notify(str(error), DANGER)
        self.load_collections(keep=True)
        self.status.notify("dropped %s" % plural(done, "collection")
                           if done > 1 else "dropped %s" % chosen[0], OK)

    def delete_database(self, window):
        """The database under the cursor, since this pane has no selection."""
        db = self.current_db
        if not db:
            return self.status.notify("nothing selected", DANGER)

        self.busy(window, "Counting %s ..." % db)
        counts = document_manager.collection_counts(self.source, db)
        total = sum(count for _, count in counts)
        body = ["  %s (%d)" % pair for pair in counts[:8]]
        if len(counts) > 8:
            body.append("  ... and %d more" % (len(counts) - 8))

        question = "DROP DATABASE %s - %s, %s ?" % (
            db, plural(len(counts), "collection"), plural(total, "document"))
        if not self.ask_yes(window, question, danger=True, body=body or None):
            return self.status.notify("not dropped")

        self.busy(window, "Dropping %s ..." % db)
        try:
            document_manager.drop_database(self.source, db)
        except MongoxError as error:
            self.load_databases(keep=True)
            return self.status.notify(str(error), DANGER)
        self.load_databases(keep=True)
        self.status.notify("dropped %s" % db, OK)

    def search(self, window):
        """Two ways in: pick a field and type a value, or write raw JSON."""
        if not self.current_coll:
            return self.status.notify("no collection selected", DANGER)

        fields = query_validator.collect_fields(
            self.source.documents(self.current_db, self.current_coll,
                                  self.query, limit=FIELD_SAMPLE))
        options = ["  (clear the filter)"] + fields + ["  raw JSON query ..."]
        choice = self.ask(window, "SEARCH IN %s" % self.current_coll, options,
                          index=1 if fields else 0,
                          hint="a field, or raw JSON for anything fancier")
        if choice is None:
            return
        if choice == 0:
            return self.apply_query(None, "")
        if choice == len(options) - 1:
            return self.raw_search(window)
        self.field_search(window, fields[choice - 1])

    def field_search(self, window, field):
        value = self.ask_text(
            window, "%s is ...   (* is a wildcard: *gas*, gas*, *gas)" % field)
        if value is None:
            return
        if not value.strip():
            return self.apply_query(None, "")
        self.apply_query(query_validator.build_field_query(field, value),
                         "%s = %s" % (field, value))

    def raw_search(self, window):
        text = self.ask_text(window, "Query as JSON, e.g. {\"status\":\"AtSea\"}")
        if text is None:
            return
        if not text.strip():
            return self.apply_query(None, "")
        try:
            query = query_validator.parse_raw_query(self.source, text)
        except MongoxError as error:
            return self.status.notify(str(error), DANGER)
        self.apply_query(query, text)

    def apply_query(self, query, label):
        previous, previous_label = self.query, self.query_label
        self.query, self.query_label = query, label
        try:
            self.load_documents()
        except Exception as error:
            self.query, self.query_label = previous, previous_label
            self.load_documents()
            return self.status.notify("search failed: %s" % error, DANGER)
        if query is None:
            return self.status.notify("filter cleared")
        self.status.notify("%d matching" % len(self.documents),
                           OK if self.documents else DIM)

    def copy(self, window):
        try:
            if self.focus == self.DOC:
                chosen = self.marked_documents()
                if chosen:
                    self.clip.copy_documents(self.source, self.current_db,
                                             self.current_coll, chosen)
                elif self.current_doc is None:
                    return self.status.notify("nothing selected", DANGER)
                else:
                    self.clip.copy_document(self.source, self.current_db,
                                            self.current_coll, self.current_doc)
            elif self.focus == self.COLL:
                chosen = self.marked_collections()
                if chosen:
                    self.busy(window, "Copying %d collections ..." % len(chosen))
                    self.clip.copy_collections(self.source, self.current_db,
                                               chosen)
                elif not self.current_coll:
                    return self.status.notify("nothing selected", DANGER)
                else:
                    self.busy(window, "Copying %s ..." % self.current_coll)
                    self.clip.copy_collection(self.source, self.current_db,
                                              self.current_coll)
            else:
                if not self.current_db:
                    return self.status.notify("nothing selected", DANGER)
                self.busy(window, "Copying %s ..." % self.current_db)
                self.clip.copy_database(self.source, self.current_db)
        except Exception as error:
            return self.status.notify("copy failed: %s" % error, DANGER)
        self.pane.clear_marks()
        self.status.notify("copied %s" % self.clip.describe(), OK)

    def paste(self, window):
        if not self.writable():
            return
        if not self.clip.full:
            return self.status.notify("nothing copied yet - press y first",
                                      DANGER)
        try:
            if self.clip.kind in (clipboard_manager.DOCUMENT, clipboard_manager.DOCUMENTS):
                self.paste_document(window)
            elif self.clip.kind == clipboard_manager.COLLECTION:
                self.paste_collection(window)
            elif self.clip.kind == clipboard_manager.COLLECTIONS:
                self.paste_collections(window)
            else:
                self.paste_database(window)
        except MongoxError as error:
            self.tell(window, "PASTE FAILED", str(error), danger=True)
        except Exception as error:
            self.status.notify("paste failed: %s" % error, DANGER)

    def paste_document(self, window):
        if not self.current_coll:
            return self.status.notify("select a collection to paste into",
                                      DANGER)
        options = ["  as a new document (fresh _id)",
                   "  keep its _id",
                   "  keep its _id, replacing anything already there"]
        choice = self.ask(window, "PASTE INTO %s" % self.current_coll, options,
                          hint="from %s" % self.clip.origin)
        if choice is None:
            return
        mode = [clipboard_manager.NEW_ID, clipboard_manager.KEEP_ID,
                clipboard_manager.REPLACE][choice]
        if self.clip.kind == clipboard_manager.DOCUMENTS:
            self.busy(window, "Pasting %d documents ..." % self.clip.count)
            done = self.clip.paste_documents(self.source, self.current_db,
                                             self.current_coll, mode)
            note = "pasted %d documents into %s.%s" % (done, self.current_db,
                                                       self.current_coll)
        else:
            self.clip.paste_document(self.source, self.current_db,
                                     self.current_coll, mode)
            note = "pasted into %s.%s" % (self.current_db, self.current_coll)
        self.load_collections(keep=True)
        self.status.notify(note, OK)

    def paste_collections(self, window):
        """Several collections keep the names they were copied under."""
        if not self.current_db:
            return self.status.notify("select a database to paste into", DANGER)
        mode = self.resolve_clash(window, self.current_db, None)
        if mode is None:
            return
        self.busy(window, "Pasting %d collections ..."
                  % len(self.clip.header["collections"]))
        self.clip.paste_blob(self.source, self.current_db, None, mode)
        self.load_collections(keep=True)
        self.status.notify("pasted %d collections into %s"
                           % (len(self.clip.header["collections"]),
                              self.current_db), OK)

    def paste_collection(self, window):
        if not self.current_db:
            return self.status.notify("select a database to paste into", DANGER)
        name = self.ask_text(window, "Paste into %s as which collection?"
                             % self.current_db, self.clip.default_name())
        if name is None or not name.strip():
            return
        name = name.strip()
        rename = {self.clip.coll_name: name}
        mode = self.resolve_clash(window, self.current_db, rename)
        if mode is None:
            return
        self.busy(window, "Pasting %s ..." % name)
        self.clip.paste_blob(self.source, self.current_db, rename, mode)
        self.load_collections(keep=True)
        self.status.notify("pasted %s into %s" % (name, self.current_db), OK)

    def paste_database(self, window):
        name = self.ask_text(window, "Paste as which database on %s?"
                             % self.source.label, self.clip.default_name())
        if name is None or not name.strip():
            return
        name = name.strip()
        mode = self.resolve_clash(window, name, None)
        if mode is None:
            return
        self.busy(window, "Pasting %s ..." % name)
        self.clip.paste_blob(self.source, name, None, mode)
        self.load_databases(keep=True)
        self.status.notify("pasted %d docs into %s" % (self.clip.count, name),
                           OK)

    def resolve_clash(self, window, into_db, rename):
        clashes = self.clip.would_clash(self.source, into_db, rename)
        return self.ask_overwrite(window, into_db, clashes)

    def ask_overwrite(self, window, into_db, clashes):
        if not clashes:
            return backup_manager.SKIP
        listed = ", ".join(clashes[:4]) + ("..." if len(clashes) > 4 else "")
        options = ["  replace them (the existing documents are dropped)",
                   "  add to them (keep what is there)",
                   "  cancel"]
        choice = self.ask(window, "ALREADY THERE", options, index=2,
                          hint="in %s: %s" % (into_db, listed))
        if choice is None or choice == 2:
            return None
        return backup_manager.DROP if choice == 0 else backup_manager.APPEND

    def copy_json(self, window):
        """The selected document, or everything shown in the collection."""
        if self.focus == self.DB:
            return self.status.notify(
                "J copies a document or a collection, not a database", DANGER)

        chosen = self.marked_documents() if self.focus == self.DOC else []
        if chosen:
            text = self.as_json_array(chosen)
            what = "%d selected documents" % len(chosen)
        elif self.focus == self.DOC:
            if self.current_doc is None:
                return self.status.notify("nothing selected", DANGER)
            text, what = self.source.to_json(self.current_doc), "1 document"
        else:
            text, what = self.shown_as_json()

        if text is None:
            return

        if len(text.encode("utf-8")) > CLIP_WARN_BYTES:
            size = human(len(text.encode("utf-8")))
            if not self.ask_yes(window, "Copy %s to the clipboard?" % size,
                                body=["That is large enough that some "
                                      "clipboard managers will struggle.",
                                      "For a whole collection, b writes a "
                                      ".mongo file instead."]):
                return self.status.notify("not copied")

        status, detail = sysclip.copy(text)

        if status == "tool":
            return self.status.notify("copied %s as JSON  (%s)" % (what, detail),
                                      OK)
        if status == "osc52":
            # Terminals do not confirm OSC 52, so the copy is reported as
            # unconfirmed.
            return self.tell(window, "PROBABLY NOT COPIED",
                             "\n".join(sysclip.why_nothing(
                                 len(text.encode("utf-8")))), danger=True)
        if detail:
            return self.tell(window, "CLIPBOARD FAILED", detail, danger=True)
        self.tell(window, "NO CLIPBOARD",
                  "\n".join(sysclip.why_nothing(len(text.encode("utf-8")))),
                  danger=True)

    def shown_as_json(self):
        """Every document listed, so it follows the search and the display limit."""
        if not self.documents:
            self.status.notify("no documents here", DANGER)
            return None, None
        note = "%d documents" % len(self.documents)
        if self.query:
            note += " matching the search"
        return self.as_json_array(self.whole(self.documents)), note

    def as_json_array(self, documents):
        return json_array(self.source, documents)

    def backup(self, window):
        """The whole database from the databases pane, otherwise the collection."""
        if not self.current_db:
            return self.status.notify("nothing selected", DANGER)

        if self.focus == self.DB:
            names = self.source.collections(self.current_db)
            if not names:
                return self.status.notify("%s has no collections"
                                          % self.current_db, DANGER)
            default = "%s.mongo" % self.current_db
            what = "%s (%d collections)" % (self.current_db, len(names))
        elif self.marked_collections():
            names = self.marked_collections()
            default = "%s.mongo" % self.current_db
            what = "%d collections from %s" % (len(names), self.current_db)
        else:
            if not self.current_coll:
                return self.status.notify("no collection selected", DANGER)
            names = [self.current_coll]
            default = "%s.%s.mongo" % (self.current_db, self.current_coll)
            what = "%s.%s" % (self.current_db, self.current_coll)

        path = files.save_file(window, lambda: self.draw(window), default,
                               title="BACK UP %s" % what.upper())
        if path is None:
            return
        if os.path.exists(path):
            if not self.ask_yes(window, "%s exists. Overwrite it?"
                                % os.path.basename(path), danger=True):
                return self.status.notify("not written")

        self.busy(window, "Backing up %s ..." % what)
        try:
            header = backup_manager.backup(self.source, self.current_db, names, path)
        except Exception as error:
            return self.tell(window, "BACKUP FAILED", str(error), danger=True)

        total = sum(entry["count"] for entry in header["collections"])
        self.status.notify("wrote %s  -  %d docs, %s"
                           % (path, total, human(os.path.getsize(path))), OK)

    def import_file(self, window):
        """Shows what is in the file before anything is written, which is also
        how a file is inspected."""
        if not self.writable():
            return

        path = files.open_file(window, lambda: self.draw(window),
                               suffix=".mongo", title="IMPORT A .mongo FILE")
        if path is None:
            return
        try:
            header = backup_manager.read_header(path)
        except Exception as error:
            return self.tell(window, "CANNOT READ IT", str(error), danger=True)

        if not self.show_file(window, path, header):
            return

        into = self.ask_text(window, "Restore into which database?",
                             header["database"])
        if into is None or not into.strip():
            return
        into = into.strip()

        clashes = backup_manager.clashes(self.source, header, into)
        mode = self.ask_overwrite(window, into, clashes)
        if mode is None:
            return

        self.busy(window, "Restoring into %s ..." % into)
        try:
            total = backup_manager.restore(self.source, path, into=into, mode=mode)
        except Exception as error:
            return self.tell(window, "RESTORE FAILED", str(error), danger=True)

        self.load_databases(keep=True)
        self.status.notify("restored %d docs into %s" % (total, into), OK)

    def show_file(self, window, path, header):
        """False means the user only wanted a look."""
        lines = ["file:      %s   (%s)" % (os.path.basename(path),
                                           human(os.path.getsize(path))),
                 "database:  %s" % header["database"],
                 "taken:     %s" % header.get("created", "?"), ""]
        for entry in header["collections"][:10]:
            lines.append("  %-24s %7d docs  %9s  %d indexes"
                         % (entry["name"], entry["count"],
                            human(entry["bytes"]),
                            len(entry.get("indexes", []))))
        if len(header["collections"]) > 10:
            lines.append("  ... and %d more" % (len(header["collections"]) - 10))

        total = sum(entry["count"] for entry in header["collections"])
        lines += ["", "%d documents in %d collection(s)."
                  % (total, len(header["collections"]))]
        return self.ask_yes(window, "Restore this? (n just closes)", body=lines)

    def unlock(self, window):
        if not self.read_only:
            return
        if self.ask_yes(window, "Unlock writes on this connection?", danger=True):
            self.read_only = False
            self.status.notify("writes unlocked", DANGER)

    def show_help(self, window):
        self.tell(window, "KEYS", HELP)

    def busy(self, window, text):
        self.status.notify(text)
        height, width = window.getmaxyx()
        self.status.draw(window, height - 1, width)
        window.refresh()

    # Modals draw straight onto the screen, so one opened after another would
    # leave the first one's frame behind. Repaint before each.

    def ask(self, window, *args, **kwargs):
        self.draw(window)
        return widgets.choose(window, *args, **kwargs)

    def ask_text(self, window, *args, **kwargs):
        self.draw(window)
        return widgets.prompt(window, *args, **kwargs)

    def ask_yes(self, window, *args, **kwargs):
        self.draw(window)
        return widgets.confirm(window, *args, **kwargs)

    def tell(self, window, *args, **kwargs):
        self.draw(window)
        return widgets.message(window, *args, **kwargs)

    def handle_selecting(self, window, key):
        """Keys while selecting. Only these work, so nothing acts on the row
        under the cursor by mistake."""
        if key == 27:
            self.end_select()
            return self.status.notify("selection cancelled") or True
        if key == ord("q"):
            return False

        if key in (curses.KEY_DOWN, ord("j")):
            self.move(1)
        elif key in (curses.KEY_UP, ord("k")):
            self.move(-1)
        elif key == ord("g"):
            self.jump(0)
        elif key == ord("G"):
            self.jump(len(self.pane.rows) - 1)
        elif key == ord(" "):
            self.pane.toggle()
            self.status.notify("%d selected" % len(self.pane.marked),
                               OK if self.pane.marked else DIM)
        elif key in (ord("y"), ord("J"), ord("b"), ord("d"), curses.KEY_DC):
            if not self.pane.marked:
                return self.status.notify("nothing picked yet - space picks",
                                          DANGER) or True
            action = {ord("y"): self.copy, ord("J"): self.copy_json,
                      ord("b"): self.backup, ord("d"): self.delete,
                      curses.KEY_DC: self.delete}[key]
            action(window)
            # end_select must not wipe what the action just reported.
            held = self.status.message, self.status.slot
            self.end_select()
            self.status.message, self.status.slot = held
        else:
            self.status.notify("selecting - space picks, esc leaves", DIM)
        return True

    def handle(self, window, key):
        """False means leave the browser."""
        self.status.clear()

        if self.selecting:
            return self.handle_selecting(window, key)
        if key in (ord("q"), 27):
            return False
        if key == ord(" "):
            self.begin_select(window)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.move(1)
        elif key in (curses.KEY_UP, ord("k")):
            self.move(-1)
        elif key in (curses.KEY_RIGHT, ord("l"), 9, 10, 13, curses.KEY_ENTER):
            self.switch(1)
        elif key in (curses.KEY_LEFT, ord("h"), curses.KEY_BTAB):
            self.switch(-1)
        elif key == ord("g"):
            self.jump(0)
        elif key == ord("G"):
            self.jump(len(self.pane.rows) - 1)
        elif key == curses.KEY_NPAGE:
            self.preview.scroll(5) if self.focus == self.DOC else self.move(10)
        elif key == curses.KEY_PPAGE:
            self.preview.scroll(-5) if self.focus == self.DOC else self.move(-10)
        elif key == ord("e"):
            self.edit(window)
        elif key in (ord("d"), curses.KEY_DC):
            self.delete(window)
        elif key == ord("y"):
            self.copy(window)
        elif key == ord("p"):
            self.paste(window)
        elif key == ord("J"):
            self.copy_json(window)
        elif key == ord("b"):
            self.backup(window)
        elif key == ord("i"):
            self.import_file(window)
        elif key == ord("/"):
            self.search(window)
        elif key == ord("r"):
            self.load_databases(keep=True)
            self.status.notify("reloaded", OK)
        elif key == ord("w"):
            self.unlock(window)
        elif key in (ord("?"), curses.KEY_F1):
            self.show_help(window)
        elif key == ord("c"):
            self.outcome = SWITCH
            return False
        return True


def run(source, read_only=False, clip=None):
    """Returns SWITCH when the user asked for the connection list."""
    outcome = {}

    def loop(window):
        curses.curs_set(0)
        theme.init()
        window.keypad(True)
        # The picker leaves a timeout on stdscr for its spinner. Cleared here,
        # or getch returns -1 and closes any modal waiting for a key.
        window.timeout(-1)
        browser = Browser(source, read_only, clip)
        while True:
            browser.draw(window)
            try:
                key = window.getch()
            except KeyboardInterrupt:
                break
            if key == curses.KEY_RESIZE:
                continue
            if not browser.handle(window, key):
                break
        outcome["value"] = browser.outcome

    curses.wrapper(loop)
    return outcome.get("value")
