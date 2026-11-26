/* ==========================================================================
   The Archives — playtest password screen
   Copied into the playtest build by tools/build_playtest.py. The site's data
   (data/archives.locked.js) is encrypted; the password decrypts it in the
   browser, then the normal site (js/app.js) starts.
   ========================================================================== */
(function () {
  "use strict";
  const KEY = "archives-playtest-password";
  const locked = window.ARCHIVES_LOCKED;
  const box = document.getElementById("pt-lock");
  const form = document.getElementById("pt-lock-form");
  const input = document.getElementById("pt-lock-password");
  const remember = document.getElementById("pt-lock-remember");
  const msg = document.getElementById("pt-lock-msg");
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

  async function unlock(password) {
    const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
    const key = await crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(locked.salt), iterations: locked.iter, hash: "SHA-256" },
      base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(locked.iv) }, key, b64(locked.data));
    return JSON.parse(new TextDecoder().decode(plain));
  }

  function start(data) {
    window.ARCHIVES = data;
    box.remove();
    document.body.classList.remove("pt-locked");
    const s = document.createElement("script");
    s.src = "js/app.js";
    document.body.appendChild(s);
  }

  async function tryPassword(password, saved) {
    try {
      const data = await unlock(password);
      try {
        if (saved || remember.checked) localStorage.setItem(KEY, password);
        else localStorage.removeItem(KEY);
      } catch (e) { /* private mode */ }
      start(data);
      return true;
    } catch (e) {
      if (saved) { try { localStorage.removeItem(KEY); } catch (e2) { /* private mode */ } }
      return false;
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    msg.textContent = "Unlocking…";
    if (!(await tryPassword(input.value, false))) {
      msg.textContent = "That password didn't work.";
      input.select();
    }
  });

  (async () => {
    let saved = null;
    try { saved = localStorage.getItem(KEY); } catch (e) { /* private mode */ }
    if (saved && (await tryPassword(saved, true))) return;
    box.hidden = false;
    input.focus();
  })();
})();
