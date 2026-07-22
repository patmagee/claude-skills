import { join } from "node:path";

export function repoPaths(root: string) {
  return {
    skillsRoot: join(root, "skills"),
    pluginJson: join(root, ".claude-plugin", "plugin.json"),
    marketplaceJson: join(root, ".claude-plugin", "marketplace.json"),
    packageJson: join(root, "package.json"),
    readme: join(root, "README.md"),
    cursorOut: join(root, "dist", "cursor"),
  };
}
