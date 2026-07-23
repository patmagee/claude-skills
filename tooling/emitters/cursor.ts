import { stringify } from "yaml";
import type { Skill } from "../schema.js";

export function renderCursorMdc(skill: Skill): string {
  const fm = skill.frontmatter;
  const frontmatter = stringify({
    description: fm.description,
    alwaysApply: false,
  }).trimEnd();
  return `---\n${frontmatter}\n---\n\n${skill.body.trim()}\n`;
}
