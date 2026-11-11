const SPECIAL = /[.+^$()|[\]\\]/g;

function expandBraces(glob) {
  const match = /\{([^{}]*)\}/.exec(glob);
  if (!match) return [glob];
  const [whole, inner] = match;
  return inner.split(",").flatMap((alt) => expandBraces(glob.replace(whole, alt)));
}

function segmentToRegExp(segment) {
  return segment
    .replace(SPECIAL, "\\$&")
    .replace(/\*/g, "[^/]*")
    .replace(/\?/g, "[^/]");
}

function buildRegExp(glob) {
  const sources = expandBraces(glob).map((variant) => {
    if (variant === "**") return ".*";
    const parts = variant.split("/").map((segment) => {
      if (segment === "**") return "(?:.*/)?";
      return `${segmentToRegExp(segment)}/`;
    });
    const joined = parts.join("").replace(/\/$/, "");
    return joined.replace(/\/\(\?:\.\*\/\)\?$/, "(?:/.*)?").replace(/\/\(\?:\.\*\/\)\?/g, "/(?:.*/)?");
  });
  return new RegExp(`^(?:${sources.join("|")})$`);
}

const compiled = new Map();

export function compileGlob(glob) {
  if (!compiled.has(glob)) compiled.set(glob, buildRegExp(glob));
  return compiled.get(glob);
}

export function globToRegExp(glob) {
  return compileGlob(glob);
}

export function matchesAny(path, globs) {
  return globs.some((glob) => compileGlob(glob).test(path));
}
