import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import matter from "gray-matter";
import { normalizeFrontmatter, type Skill } from "./schema.js";

export function loadSkill(dir: string): Skill {
  const slug = basename(dir);
  const raw = readFileSync(join(dir, "SKILL.md"), "utf8");
  const { data, content } = matter(raw);
  return {
    slug,
    dir,
    body: content,
    frontmatter: normalizeFrontmatter(data, slug),
  };
}

export function loadSkills(skillsRoot: string): Skill[] {
  return readdirSync(skillsRoot, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => join(skillsRoot, e.name))
    .filter((dir) => existsSync(join(dir, "SKILL.md")))
    .map(loadSkill)
    .sort((a, b) => a.slug.localeCompare(b.slug));
}
