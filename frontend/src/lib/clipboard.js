// Safe clipboard copy that works inside sandboxed iframes (Emergent preview,
// permissions-policy-restricted contexts, http-served previews, etc.).
// Falls back to document.execCommand('copy') with a hidden textarea.
export async function safeCopy(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return { ok: true };
    }
  } catch (_) { /* swallow & fall through to execCommand */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "-9999px";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    if (!ok) throw new Error("execCommand returned false");
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message || "Copy blocked" };
  }
}
