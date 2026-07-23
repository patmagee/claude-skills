import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generate } from "./generate.js";

let root: string;

function writeSkill(slug: string, frontmatter: string, body = "# Body\n") {
  const dir = join(root, "skills", slug);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "SKILL.md"), `---\n${frontmatter}\n---\n\n${body}`);
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "skills-gen-"));
  mkdirSync(join(root, "skills"), { recursive: true });
  mkdirSync(join(root, ".claude-plugin"), { recursive: true });
  writeFileSync(join(root, "package.json"), JSON.stringify({ version: "1.0.0" }));
  writeFileSync(
    join(root, ".claude-plugin", "plugin.json"),
    JSON.stringify({ version: "1.0.0", skills: [] }, null, 2),
  );
  writeFileSync(
    join(root, ".claude-plugin", "marketplace.json"),
    JSON.stringify({ plugins: [{ version: "1.0.0" }] }, null, 2),
  );
  writeFileSync(
    join(root, "README.md"),
    "# Repo\n\n<!-- SKILLS:START -->\nOLD\n<!-- SKILLS:END -->\n",
  );
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe("generate", () => {
  it("emits codex and cursor artifacts and updates aggregates", () => {
    writeSkill("alpha", "name: alpha\ndescription: Alpha does things. Detail.");
    writeSkill(
      "beta",
      "name: beta\ndescription: Beta run.\ninvocation: user\nharnesses: [claude, codex]",
    );

    generate(root);

    expect(existsSync(join(root, "skills", "alpha", "agents", "openai.yaml"))).toBe(true);
    expect(existsSync(join(root, "dist", "cursor", "alpha.mdc"))).toBe(true);
    // beta opts out of cursor
    expect(existsSync(join(root, "dist", "cursor", "beta.mdc"))).toBe(false);
    expect(existsSync(join(root, "skills", "beta", "agents", "openai.yaml"))).toBe(true);

    const plugin = JSON.parse(readFileSync(join(root, ".claude-plugin", "plugin.json"), "utf8"));
    expect(plugin.skills).toEqual(["./skills/alpha", "./skills/beta"]);

    const readme = readFileSync(join(root, "README.md"), "utf8");
    expect(readme).toContain("[alpha](skills/alpha/SKILL.md)");
    expect(readme).not.toContain("OLD");
  });

  it("removes orphaned artifacts when a skill drops harnesses", () => {
    writeSkill("alpha", "name: alpha\ndescription: Alpha does things. Detail.");
    generate(root);
    expect(existsSync(join(root, "dist", "cursor", "alpha.mdc"))).toBe(true);
    expect(existsSync(join(root, "skills", "alpha", "agents", "openai.yaml"))).toBe(true);

    // alpha drops codex + cursor, keeping only claude
    writeSkill(
      "alpha",
      "name: alpha\ndescription: Alpha does things. Detail.\nharnesses: [claude]",
    );
    generate(root);

    expect(existsSync(join(root, "dist", "cursor", "alpha.mdc"))).toBe(false);
    expect(existsSync(join(root, "skills", "alpha", "agents", "openai.yaml"))).toBe(false);
  });

  it("throws when manifest versions are out of sync", () => {
    writeFileSync(
      join(root, ".claude-plugin", "plugin.json"),
      JSON.stringify({ version: "9.9.9", skills: [] }, null, 2),
    );
    writeSkill("alpha", "name: alpha\ndescription: Alpha. Detail.");
    expect(() => generate(root)).toThrow(/mismatch/i);
  });
});
