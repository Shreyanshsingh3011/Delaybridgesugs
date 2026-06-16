"""Minimal async MongoDB(Motor)-compatible data layer backed by Supabase (PostgREST).

Each "collection" maps to a Postgres table named ``{PREFIX}{collection}`` with shape
(id text primary key, data jsonb, created_at timestamptz). This lets the existing
FastAPI code keep calling db.<collection>.find_one/find/insert_one/update_one/delete_one
without rewriting query logic. Collections here are small, so non-id filters are
resolved in Python.
"""
import os
import uuid
import httpx

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "https://efjkhbyhgyqesmawztny.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVmamto"
    "YnloZ3lxZXNtYXd6dG55Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODExNTkzMTgsImV4cCI6MjA5"
    "NjczNTMxOH0.bOFGz9XjZnBwqPv32UDX0_Xqn63POLXP1Cq-c_mnH2k"
)
PREFIX = os.environ.get("SUPABASE_TABLE_PREFIX", "dbridge_")

KEY_FIELDS = {
    "users": "id",
    "sessions": "id",
    "chat_logs": "id",
    "alert_log": "id",
}


def _headers(extra=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _get_path(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_path(doc, path, value):
    parts = path.split(".")
    cur = doc
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _match(doc, flt):
    if not flt:
        return True
    for k, v in flt.items():
        if isinstance(v, (dict, list)):
            continue  # operator/complex filters not used for matching here
        if "." in k:
            head, rest = k.split(".", 1)
            arr = doc.get(head)
            if isinstance(arr, list):
                # array filter: match if any element's sub-path equals v (e.g. "sheets.label")
                if not any(isinstance(el, dict) and str(_get_path(el, rest)) == str(v) for el in arr):
                    return False
                continue
        if str(_get_path(doc, k)) != str(v):
            return False
    return True


def _apply_projection(doc, projection):
    if not doc or not projection:
        return doc
    # only exclusion projections (value 0) are used in this codebase
    excluded = [k for k, v in projection.items() if v in (0, False)]
    if not excluded:
        return doc
    out = dict(doc)
    for k in excluded:
        out.pop(k, None)
    return out


def _apply_update(doc, update):
    out = dict(doc or {})
    if "$set" in update:
        for k, v in update["$set"].items():
            if "." in k:
                _set_path(out, k, v)
            else:
                out[k] = v
    if "$inc" in update:
        for k, v in update["$inc"].items():
            out[k] = (out.get(k) or 0) + v
    if "$push" in update:
        for k, v in update["$push"].items():
            arr = out.get(k)
            if not isinstance(arr, list):
                arr = []
            arr.append(v)
            out[k] = arr
    if "$unset" in update:
        for k in update["$unset"].keys():
            out.pop(k, None)
    if not any(op in update for op in ("$set", "$inc", "$push", "$unset")):
        return dict(update)  # full-document replacement
    return out


class _Result:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _strip_positional(update):
    """Return a copy of `update` with positional ($) $set keys removed."""
    if "$set" not in update:
        return update
    out = {k: v for k, v in update.items() if k != "$set"}
    rest = {k: v for k, v in update["$set"].items() if ".$." not in k}
    if rest:
        out["$set"] = rest
    return out


def _apply_positional(doc, flt, update):
    """Apply Mongo positional array updates like {"$set": {"sheets.$.rows": n}} where the
    matched array element is selected by an array filter in `flt` like {"sheets.label": "A"}."""
    out = dict(doc or {})
    set_ops = update.get("$set", {})
    positional = {k: v for k, v in set_ops.items() if ".$." in k}
    if not positional:
        return out
    arr_name = next(iter(positional)).split(".$.")[0]
    arr = list(out.get(arr_name) or [])
    # locate the target element via the array filter in flt (e.g. "sheets.label")
    idx = None
    for fk, fv in (flt or {}).items():
        if fk.startswith(arr_name + ".") and not isinstance(fv, (dict, list)):
            sub = fk.split(".", 1)[1]
            for i, el in enumerate(arr):
                if isinstance(el, dict) and str(el.get(sub)) == str(fv):
                    idx = i
                    break
            break
    if idx is None:
        return out
    el = dict(arr[idx])
    for k, v in positional.items():
        field = k.split(".$.", 1)[1]
        if "." in field:
            _set_path(el, field, v)
        else:
            el[field] = v
    arr[idx] = el
    out[arr_name] = arr
    return out


class Cursor:
    def __init__(self, coll, flt, projection=None):
        self.coll = coll
        self.flt = flt or {}
        self.projection = projection
        self._sort = None
        self._limit = None

    def sort(self, field, direction=1):
        self._sort = (field, direction)
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def _load(self):
        docs = await self.coll._query(self.flt)
        if self._sort:
            field, direction = self._sort
            docs = sorted(docs, key=lambda d: (d.get(field) is None, d.get(field)),
                          reverse=(direction < 0))
        if self._limit is not None:
            docs = docs[: self._limit]
        return [_apply_projection(d, self.projection) for d in docs]

    def __aiter__(self):
        return self._agen()

    async def _agen(self):
        for d in await self._load():
            yield d

    async def to_list(self, length=None):
        docs = await self._load()
        return docs if length is None else docs[:length]


class Collection:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.table = f"{PREFIX}{name}"
        self.key = KEY_FIELDS.get(name, "id")

    @property
    def _url(self):
        return f"{SUPABASE_URL}/rest/v1/{self.table}"

    async def _query(self, flt):
        params = [("select", "*"), ("limit", "100000")]
        flt = flt or {}
        if self.key in flt and not isinstance(flt[self.key], (dict, list)):
            params.append(("id", f"eq.{flt[self.key]}"))
        r = await self.db.client.get(self._url, params=params, headers=_headers())
        r.raise_for_status()
        rows = r.json()
        docs = [row["data"] for row in rows]
        return [d for d in docs if _match(d, flt)]

    async def find_one(self, flt, projection=None):
        docs = await self._query(flt)
        return _apply_projection(docs[0], projection) if docs else None

    def find(self, flt=None, projection=None):
        return Cursor(self, flt or {}, projection)

    async def insert_one(self, doc):
        row_id = str(doc.get(self.key) or doc.get("id") or uuid.uuid4())
        body = {"id": row_id, "data": doc}
        r = await self.db.client.post(
            self._url, json=body,
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        )
        r.raise_for_status()
        return _Result(inserted_id=row_id, acknowledged=True)

    async def update_one(self, flt, update, upsert=False):
        docs = await self._query(flt)
        if docs:
            existing = docs[0]
            row_id = str(existing.get(self.key) or existing.get("id"))
            new_doc = _apply_positional(existing, flt, update)
            new_doc = _apply_update(new_doc, _strip_positional(update))
            r = await self.db.client.patch(
                self._url, params=[("id", f"eq.{row_id}")], json={"data": new_doc},
                headers=_headers({"Prefer": "return=minimal"}),
            )
            r.raise_for_status()
            return _Result(matched_count=1, modified_count=1, acknowledged=True)
        if upsert:
            base = {k: v for k, v in (flt or {}).items() if not isinstance(v, (dict, list))}
            new_doc = _apply_update(base, update)
            res = await self.insert_one(new_doc)
            return _Result(matched_count=0, modified_count=0, upserted_id=res.inserted_id,
                           acknowledged=True)
        return _Result(matched_count=0, modified_count=0, acknowledged=True)

    async def delete_one(self, flt):
        docs = await self._query(flt)
        if not docs:
            return _Result(deleted_count=0, acknowledged=True)
        row_id = str(docs[0].get(self.key) or docs[0].get("id"))
        r = await self.db.client.delete(
            self._url, params=[("id", f"eq.{row_id}")],
            headers=_headers({"Prefer": "return=minimal"}),
        )
        r.raise_for_status()
        return _Result(deleted_count=1, acknowledged=True)

    async def create_index(self, *args, **kwargs):
        return None  # indexes are managed in Postgres; no-op here


class SupaDB:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY env vars are required")
        self.client = httpx.AsyncClient(timeout=30.0)
        self._collections = {}

    def __getattr__(self, name):
        # Called only for attributes not found normally (e.g. db.users)
        if name.startswith("_") or name in ("client",):
            raise AttributeError(name)
        cols = self.__dict__.setdefault("_collections", {})
        if name not in cols:
            cols[name] = Collection(self, name)
        return cols[name]

    async def raw_select(self, name, filters=None):
        """Query a Postgres view or table directly via PostgREST."""
        params = [("select", "*")]
        for k, v in (filters or {}).items():
            params.append((k, f"eq.{v}"))
        r = await self.client.get(f"{SUPABASE_URL}/rest/v1/{name}", params=params, headers=_headers())
        r.raise_for_status()
        return r.json()

    async def rpc(self, fn_name, args=None):
        """Call a Postgres function via PostgREST /rpc/."""
        r = await self.client.post(f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}", json=args or {}, headers=_headers())
        r.raise_for_status()
        return r.json()

    async def aclose(self):
        try:
            await self.client.aclose()
        except Exception:
            pass
