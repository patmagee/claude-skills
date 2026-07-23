import type { Skill } from "./schema.js";

export const README_START = "<!-- SKILLS:START -->";
export const README_END = "<!-- SKILLS:END -->";

export function pluginSkillPaths(skills: Skill[]): string[] {
  return skills
    .filter((s) => s.frontmatter.harnesses.includes("claude"))
    .map((s) => `./skills/${s.slug}`)
    .sort();
}

function escapeCell(text: string): string {
  return text.replace(/\|/g, "\\|");
}

export function renderReadmeTable(skills: Skill[]): string {
  const header = "| Skill | Description | Invocation |";
  const divider = "| --- | --- | --- |";
  const rows = skills.map((s) => {
    const link = `[${s.slug}](skills/${s.slug}/SKILL.md)`;
    return `| ${link} | ${escapeCell(s.frontmatter.shortDescription)} | ${s.frontmatter.invocation} |`;
  });
  return [header, divider, ...rows].join("\n");
}

export function replaceBetweenMarkers(
  text: string,
  start: string,
  end: string,
  replacement: string,
): string {
  const startIdx = text.indexOf(start);
  const endIdx = text.indexOf(end);
  if (startIdx === -1 || endIdx === -1 || endIdx < startIdx) {
    throw new Error(`Missing or out-of-order markers: "${start}" / "${end}"`);
  }
  const before = text.slice(0, startIdx + start.length);
  const after = text.slice(endIdx);
  return `${before}\n${replacement}\n${after}`;
}

export function checkVersionSync(
  versions: Record<string, string>,
): { ok: boolean; message?: string } {
  const entries = Object.entries(versions);
  const unique = [...new Set(entries.map(([, v]) => v))];
  if (unique.length <= 1) return { ok: true };
  const detail = entries.map(([k, v]) => `${k}=${v}`).join(", ");
  return { ok: false, message: `Version mismatch across manifests: ${detail}` };
}
