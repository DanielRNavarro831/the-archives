/*
 * Encrypts the playtest site's data with the playtest password (used by tools/build_playtest.py).
 *
 *   PT_PASSWORD=... node tools/playtest/encrypt.js <data.json> <out.js>
 *
 * AES-256-GCM with a key from PBKDF2-SHA256, the same as the browser's Web Crypto API uses to
 * unlock it (tools/playtest/unlock.js). Only Node's built-in crypto module is used.
 */
const fs = require("fs");
const crypto = require("crypto");

const [, , src, out] = process.argv;
const password = process.env.PT_PASSWORD;
if (!src || !out || !password) {
  console.error("usage: PT_PASSWORD=... node tools/playtest/encrypt.js <data.json> <out.js>");
  process.exit(1);
}
const ITERATIONS = 310000;
const salt = crypto.randomBytes(16);
const iv = crypto.randomBytes(12);
const key = crypto.pbkdf2Sync(password, salt, ITERATIONS, 32, "sha256");
const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
const body = Buffer.concat([cipher.update(fs.readFileSync(src)), cipher.final(), cipher.getAuthTag()]);
const locked = { v: 1, iter: ITERATIONS, salt: salt.toString("base64"), iv: iv.toString("base64"), data: body.toString("base64") };
fs.writeFileSync(out, "// The Archives playtest data, encrypted. Unlocked in the browser by js/unlock.js.\n" +
  `window.ARCHIVES_LOCKED = ${JSON.stringify(locked)};\n`);
console.log(`encrypted ${fs.statSync(src).size} bytes -> ${out}`);
