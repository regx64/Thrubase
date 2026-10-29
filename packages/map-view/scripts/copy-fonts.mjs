// Copies the font files the design system ships (OFL-1.1, CC BY 4.0) from node_modules into
// src/fonts/, where styles.css picks them up. Codicons come with @vscode/codicons' CSS.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const fonts = join(root, "src", "fonts");
mkdirSync(fonts, { recursive: true });
const files = [
  ["@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2", "JetBrainsMono-latin-wght.woff2"],
  ["pretendard/dist/web/variable/woff2/PretendardVariable.woff2", "PretendardVariable.woff2"],
];
for (const [src, name] of files) copyFileSync(join(root, "node_modules", src), join(fonts, name));
console.log("copied fonts");
