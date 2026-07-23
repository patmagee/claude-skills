import { describe, it, expect } from "vitest";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { loadSkill, loadSkills } from "./skills.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesRoot = join(here, "__fixtures__", "skills");

describe("loadSkill", () => {
  it("parses frontmatter and body", () => {
    const skill = loadSkill(join(fixturesRoot, "good-skill"));
    expect(skill.slug).toBe("good-skill");
    expect(skill.frontmatter.name).toBe("good-skill");
    expect(skill.frontmatter.shortDescription).toBe("Does a good thing.");
    expect(skill.body.trim().startsWith("# Good Skill")).toBe(true);
  });
});

describe("loadSkills", () => {
  it("loads every skill dir sorted by slug", () => {
    const skills = loadSkills(fixturesRoot);
    expect(skills.map((s) => s.slug)).toEqual(["good-skill", "user-skill"]);
  });
});
