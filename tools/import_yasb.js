/*
 * Reads YASB's card data source files (CoffeeScript) and writes plain JSON.
 *
 *   node tools/import_yasb.js
 *
 * Input:  data/yasb/source/cards-common.coffee  (stats, slots, points)
 *         data/yasb/source/cards-en.coffee      (English card text)
 * Output: data/yasb/yasb-cards.json
 *
 * Safety: the files are only PARSED into a syntax tree; none of their code is run.
 * Only literal values (strings, numbers, lists, objects) are read; functions are skipped.
 * YASB (https://yasb.app, https://github.com/raithos/xwing) is MIT licensed.
 */
const fs = require("fs");
const path = require("path");
const CoffeeScript = require("coffeescript");

const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "data", "yasb", "source");
const SKIP = Symbol("skip");

function parse(file) {
  return CoffeeScript.compile(fs.readFileSync(path.join(SRC, file), "utf8"), { ast: true });
}

function literal(n) {
  if (!n) return SKIP;
  switch (n.type) {
    case "StringLiteral": case "NumericLiteral": case "BooleanLiteral": return n.value;
    case "NullLiteral": return null;
    case "TemplateLiteral":
      if (n.expressions.length) return SKIP;
      return n.quasis.map((q) => (q.value.cooked != null ? q.value.cooked
        : q.value.raw.replace(/\\(["'\\])/g, "$1"))).join("");
    case "UnaryExpression":
      if (n.operator === "-" && n.argument.type === "NumericLiteral") return -n.argument.value;
      return SKIP;
    case "ArrayExpression": {
      const out = [];
      for (const e of n.elements) { const v = literal(e); if (v !== SKIP) out.push(v); }
      return out;
    }
    case "ObjectExpression": {
      const out = {};
      for (const p of n.properties) {
        if (p.type !== "ObjectProperty") continue;
        const k = p.key.type === "Identifier" ? p.key.name : literal(p.key);
        if (k === SKIP) continue;
        const v = literal(p.value);
        if (v !== SKIP) out[k] = v;
      }
      return out;
    }
    default: return SKIP;   // functions, calls, references: ignored
  }
}

/** depth-first search for nodes */
function* walk(n) {
  if (!n || typeof n !== "object") return;
  if (n.type) yield n;
  for (const k of Object.keys(n)) {
    if (k === "loc" || k === "range") continue;
    const v = n[k];
    if (Array.isArray(v)) for (const x of v) yield* walk(x);
    else if (v && typeof v === "object") yield* walk(v);
  }
}

const memberName = (n) => n.type === "MemberExpression" ? memberName(n.object) + "." + (n.property.name || n.property.value)
  : n.type === "Identifier" ? n.name : "?";

// ---- cards-common: exportObj.basicCardData = -> { ships:, pilotsById:, ... }
const common = parse("cards-common.coffee");
let basic = null;
for (const n of walk(common)) {
  if (n.type === "AssignmentExpression" && memberName(n.left) === "exportObj.basicCardData") {
    for (const m of walk(n.right)) {
      if (m.type === "ObjectExpression" && m.properties.some((p) => p.key && p.key.name === "pilotsById")) { basic = literal(m); break; }
    }
  }
}
if (!basic) throw new Error("basicCardData not found");

// ---- cards-en: pilot_translations = {...} etc. inside cardLoaders.English
const en = parse("cards-en.coffee");
const tr = {};
for (const n of walk(en)) {
  if (n.type === "AssignmentExpression" && n.left.type === "Identifier" && /_translations$/.test(n.left.name)) {
    tr[n.left.name] = literal(n.right);
  }
}

const out = {
  source: "YASB (https://yasb.app) — github.com/raithos/xwing, MIT License",
  commit: fs.readFileSync(path.join(SRC, "COMMIT"), "utf8").trim(),
  importedAt: new Date().toISOString().slice(0, 10),
  ...basic,
  translations: tr,
};
fs.writeFileSync(path.join(ROOT, "data", "yasb", "yasb-cards.json"), JSON.stringify(out, null, 1));
console.log(Object.entries(out).map(([k, v]) => `${k}=${Array.isArray(v) ? v.length : typeof v === "object" ? Object.keys(v).length : v}`).join("  "));
console.log("translations:", Object.entries(tr).map(([k, v]) => `${k}=${Object.keys(v).length}`).join("  "));
