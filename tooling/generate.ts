import {
  writeFileSync,
  readFileSync,
  mkdirSync,
  readdirSync,
  rmSync,
  existsSync,
} from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadSkills } from "./skills.js";
import { renderCodexYaml } from "./emitters/codex.js";
import { renderCursorMdc } from "./emitters/cursor.js";
import {
  pluginSkillPaths,
  renderReadmeTable,
  replaceBetweenMarkers,
  checkVersionSync,
  README_START,
  README_END,
} from "./aggregates.js";
import { repoPaths } from "./paths.js";

function readJson(path: string): any {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function generate(root: string): void {
  const paths = repoPaths(root);
  const skills = loadSkills(paths.skillsRoot);

  const pkg = readJson(paths.packageJson);
  const plugin = readJson(paths.pluginJson);
  const marketplace = readJson(paths.marketplaceJson);

  const sync = checkVersionSync({
    "package.json": pkg.version,
    "plugin.json": plugin.version,
    "marketplace.json": marketplace.plugins?.[0]?.version,
  });
  if (!sync.ok) throw new Error(sync.message);

  for (const skill of skills) {
    if (skill.frontmatter.harnesses.includes("codex")) {
      const dir = join(skill.dir, "agents");
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, "openai.yaml"), renderCodexYaml(skill));
    }
    if (skill.frontmatter.harnesses.includes("cursor")) {
      mkdirSync(paths.cursorOut, { recursive: true });
      writeFileSync(join(paths.cursorOut, `${skill.slug}.mdc`), renderCursorMdc(skill));
    }
  }

  // Remove artifacts no current skill produces, so the committed output always
  // reflects the full target state (a skill dropping a harness, or being
  // deleted, leaves no stale file behind for the CI drift check to miss).
  const expectedCursor = new Set(
    skills
      .filter((s) => s.frontmatter.harnesses.includes("cursor"))
      .map((s) => `${s.slug}.mdc`),
  );
  if (existsSync(paths.cursorOut)) {
    for (const file of readdirSync(paths.cursorOut)) {
      if (file.endsWith(".mdc") && !expectedCursor.has(file)) {
        rmSync(join(paths.cursorOut, file));
      }
    }
  }
  for (const skill of skills) {
    if (!skill.frontmatter.harnesses.includes("codex")) {
      const codexFile = join(skill.dir, "agents", "openai.yaml");
      if (existsSync(codexFile)) rmSync(codexFile);
    }
  }

  plugin.skills = pluginSkillPaths(skills);
  writeFileSync(paths.pluginJson, JSON.stringify(plugin, null, 2) + "\n");

  const readme = readFileSync(paths.readme, "utf8");
  const table = renderReadmeTable(skills);
  writeFileSync(paths.readme, replaceBetweenMarkers(readme, README_START, README_END, table));
}

const invokedDirectly =
  process.argv[1] && process.argv[1] === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  generate(process.cwd());
  console.log("Generated harness artifacts and updated aggregates.");
}
