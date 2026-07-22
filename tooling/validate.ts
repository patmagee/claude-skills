import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadSkills } from "./skills.js";
import { checkVersionSync } from "./aggregates.js";
import { repoPaths } from "./paths.js";

function readJson(path: string): any {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function validate(root: string): void {
  const paths = repoPaths(root);
  loadSkills(paths.skillsRoot); // throws on invalid frontmatter
  const pkg = readJson(paths.packageJson);
  const plugin = readJson(paths.pluginJson);
  const marketplace = readJson(paths.marketplaceJson);
  const sync = checkVersionSync({
    "package.json": pkg.version,
    "plugin.json": plugin.version,
    "marketplace.json": marketplace.plugins?.[0]?.version,
  });
  if (!sync.ok) throw new Error(sync.message);
}

const invokedDirectly =
  process.argv[1] && process.argv[1] === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  try {
    validate(process.cwd());
    console.log("All skills valid; manifest versions in sync.");
  } catch (err) {
    console.error((err as Error).message);
    process.exit(1);
  }
}
