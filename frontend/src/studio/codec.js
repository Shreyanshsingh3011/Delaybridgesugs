// Round-trip lossless Base64URL codec for the dependency graph state.
// The link IS the logic — no server persistence.

const VERSION = 1;

function b64urlEncode(str) {
  // UTF-8 safe encode
  const utf8 = unescape(encodeURIComponent(str));
  return btoa(utf8)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function b64urlDecode(str) {
  let s = String(str).replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const utf8 = atob(s);
  return decodeURIComponent(escape(utf8));
}

export function encodeState(state) {
  const minimal = {
    v: VERSION,
    src: state.source
      ? {
          u: state.source.url || "",
          h: state.source.headers || [],
          r: state.source.rowIds || [],
        }
      : null,
    g: (state.groups || []).map((x) => ({
      i: x.id,
      n: x.name,
      k: x.kind,        // 'row' | 'col'
      m: x.members,
    })),
    e: (state.edges || []).map((x) => ({
      i: x.id,
      f: x.from,        // [{t:'row'|'col'|'group', i:'id'}, ...]
      t: x.to,
      c: x.cardinality, // '1:1' | '1:N' | 'N:1' | 'N:N'
      l: x.label || "",
    })),
  };
  return b64urlEncode(JSON.stringify(minimal));
}

export function decodeState(token) {
  const raw = b64urlDecode(token);
  const j = JSON.parse(raw);
  if (!j || j.v !== VERSION) throw new Error("Unsupported share-link version.");
  return {
    source: j.src
      ? { url: j.src.u, headers: j.src.h || [], rowIds: j.src.r || [], fetchedAt: null }
      : null,
    groups: (j.g || []).map((x) => ({
      id: x.i,
      name: x.n,
      kind: x.k,
      members: x.m || [],
    })),
    edges: (j.e || []).map((x) => ({
      id: x.i,
      from: x.f || [],
      to: x.t || [],
      cardinality: x.c || "1:1",
      label: x.l || "",
    })),
  };
}

export function buildShareUrl(state) {
  const tok = encodeState(state);
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/studio#d=${tok}`;
}

export function readHashState() {
  if (typeof window === "undefined") return null;
  const h = window.location.hash || "";
  const m = h.match(/d=([^&]+)/);
  if (!m) return null;
  try { return decodeState(m[1]); } catch (e) { return null; }
}

export function clearHash() {
  if (typeof window === "undefined") return;
  if (window.location.hash) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}
