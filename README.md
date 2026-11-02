# mongox

This is basically a MongoDB browser for the terminal. It's like MongoDB Compass, but one that you can run on the VPS. I created it, cause I never liked the mongosh, I would keep forgetting the commands and how to use them. With this, you can just pick a server, search, edit, copy, back up and restore from your personal keyboard.

<img width="4581" height="2013" alt="image" src="https://github.com/user-attachments/assets/e2de33bd-2177-48ce-8885-06b443a84aef" />

## Run

    python3 mongox.py

This program requires Python and pymongo. The first screen lists what it can reach: a local MongoDB, Docker containers running one, and .vps profiles for servers behind SSH.

## Requirements

Linux, with Python 3.8 or newer. The rest depends on what you use:

| Tool | Used for | Without it |
|---|---|---|
| pymongo | Everything. mongox offers to install it on the first run | mongox doesn't start |
| docker | Listing MongoDB containers on the first screen | The first screen says Docker isn't installed |
| ssh | Opening `.vps` profiles for servers behind SSH | Those profiles can't connect |
| wl-copy on Wayland, or xclip or xsel on X11 | J, copying JSON out to other apps | mongox falls back to the terminal's clipboard code, which kitty, Alacritty and WezTerm accept and GNOME Terminal doesn't |

Copying and pasting inside mongox with y and p needs none of them.

## Levels

In the first screen, you will be able to see which Mongo databases you have access to. That would be a local MongoDB installed in your system, a Docker container running one, or a set of .vps profiles for servers behind SSH.

Once you choose which instance, you'll be able to access the instance of the MongoDB running, and within the instance you will see the databases in it. Then of course you can choose a database, and then you'll see the collections, and then on the third pane you shall see the documents.

Everything here is modifiable, deletable, editable, copyable, movable. The amazing thing about it is you can even copy a database from one instance to another. You can copy a collection from one database to another, across instances even. You can also edit the documents, delete them, use a very basic, very intuitive and easy to understand filter, etc.

The philosophy of this program is that it shall be usable; that MongoDB shall be accessible to any layman who has never used MongoDB.

## Keys

| Key | Action |
|---|---|
| j k, ↑ ↓ | Move |
| Enter, l, Tab | Open what is selected: database, collection, document |
| h, Shift-Tab | Back out one level |
| g G | First, last |
| e | Edit the document in your editor |
| y | Copy the document, collection or database |
| J | Copy as JSON |
| p | Paste what was copied |
| b | Back up to a `.mongo` file |
| i | Import a `.mongo` file |
| d | Delete |
| / | Search |
| Space | Select several rows, then y, J, b or d act on all of them |
| w | Unlock writes on a read-only connection |
| c | Back to the connection list |
| ? | Help |
| q, Esc | Leave |

## Build and install

`./build.sh` packs it into a single file in `dist/`, and `./install.sh` puts that on your PATH as `mongox`. `./compile.sh` builds a native binary with Nuitka instead, which starts faster.

---

mongox is not affiliated with or endorsed by MongoDB, Inc.
