import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // eslint-plugin-react's "detect" mode calls the removed context.getFilename()
    // API under ESLint 10, crashing every rule that checks the React version
    // (e.g. react/display-name). Pinning the version explicitly skips detection.
    settings: { react: { version: "19.2.8" } },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "coverage/**"]),
]);

export default eslintConfig;
