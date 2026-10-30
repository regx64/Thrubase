// Copies the build output (dist/) to where the two hosts serve it from.
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const targets = [
  join(root, "..", "..", "core", "src", "thrubase", "web"),
  join(root, "..", "..", "vscode", "media", "map-view"),
];
for (const target of targets) {
  if (!existsSync(dirname(target))) continue;
  rmSync(target, { recursive: true, force: true });
  mkdirSync(target, { recursive: true });
  cpSync(dist, target, { recursive: true });
  if (target.endsWith("web")) writeFileSync(join(target, ".gitkeep"), "");
  console.log(`copied dist -> ${target}`);
}
