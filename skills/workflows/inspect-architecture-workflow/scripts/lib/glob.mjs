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

export function globToRegExp(glob) {
  const sources = expandBraces(glob).map((variant) => {
    const parts = variant.split("/").map((segment) => {
      if (segment === "**") return "(?:.*/)?";
      return `${segmentToRegExp(segment)}/`;
    });
    const joined = parts.join("").replace(/\/$/, "");
    return joined.replace(/\/\(\?:\.\*\/\)\?$/, "(?:/.*)?").replace(/\/\(\?:\.\*\/\)\?/g, "/(?:.*/)?");
  });
  return new RegExp(`^(?:${sources.join("|")})$`);
}

export function matchesAny(path, globs) {
  return globs.some((glob) => globToRegExp(glob).test(path));
}
