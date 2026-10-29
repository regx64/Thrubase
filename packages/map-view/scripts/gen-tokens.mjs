// Generates src/tokens.css from tokens.json: light values on :root, dark values for
// prefers-color-scheme / [data-theme="dark"], and the VS Code theme mapping on the theme
// classes VS Code puts on the Webview <body>.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const t = JSON.parse(readFileSync(join(root, "tokens.json"), "utf8"));

const block = (selector, lines) => `${selector} {\n${lines.map((l) => `  ${l}`).join("\n")}\n}\n`;
const colorVars = (mode) => Object.entries(t.color).map(([k, v]) => `--${k}: ${v[mode]};`);
const contour = (base) => t.contour.steps.map((p, i) => `--contour-${i + 1}: color-mix(in srgb, ${base} ${p}%, transparent);`);

const statics = [
  ...Object.entries(t.font).map(([k, v]) => `--font-${k}: ${v.value};`),
  ...Object.entries(t.space).map(([k, v]) => `--space-${k}: ${v}px;`),
  ...Object.entries(t.size).map(([k, v]) => `--${k}: ${v}px;`),
  ...Object.entries(t.radius).map(([k, v]) => `--radius-${k}: ${v}px;`),
  ...Object.entries(t.motion).map(([k, v]) => `--${k}: ${v};`),
  ...Object.entries(t.type).flatMap(([k, v]) => [
    `--type-${k}: ${v.weight} ${v.size}px/${v.line}px var(--font-${v.family});`,
  ]),
];

const vscodeMapped = Object.entries(t.color).filter(([, v]) => v.vscode).map(([k, v]) => `--${k}: ${v.vscode};`);
const accent = (mode) => ["accent", "accent-ink", "accent-soft", "on-accent"].map((k) => `--${k}: ${t.color[k][mode]};`);
const vscodeFonts = Object.entries(t.font).filter(([, v]) => v.vscode).map(([k, v]) => `--font-${k}: ${v.vscode};`);

let css = "/* Generated from tokens.json by scripts/gen-tokens.mjs. Do not edit. */\n";
css += block(":root", [...colorVars("light"), ...contour("var(--ink)"), ...statics, "color-scheme: light dark;"]);
css += `@media (prefers-color-scheme: dark) {\n${block(':root:not([data-theme="light"])', colorVars("dark")).replace(/^/gm, "  ")}}\n`;
css += block(':root[data-theme="dark"]', colorVars("dark"));
css += "\n/* VS Code: neutral colors follow the user's theme; only the accent is fixed. */\n";
css += block(
  "body.vscode-light, body.vscode-dark, body.vscode-high-contrast, body.vscode-high-contrast-light",
  [...vscodeMapped, ...contour("var(--vscode-foreground)"), ...vscodeFonts],
);
css += block("body.vscode-light, body.vscode-high-contrast-light", accent("light"));
css += block("body.vscode-dark, body.vscode-high-contrast", accent("dark"));
css += block("body.vscode-light :focus-visible, body.vscode-dark :focus-visible, body.vscode-high-contrast :focus-visible, body.vscode-high-contrast-light :focus-visible", ["outline-color: var(--vscode-focusBorder);"]);
css += block("@media (prefers-reduced-motion: reduce)", []).replace("{\n\n}", "{\n  :root { --duration-fast: 0ms; --duration-base: 0ms; --duration-slow: 0ms; }\n  *, *::before, *::after { transition-duration: 0ms !important; animation-duration: 0ms !important; }\n}");

writeFileSync(join(root, "src", "tokens.css"), css);
console.log("wrote src/tokens.css");
