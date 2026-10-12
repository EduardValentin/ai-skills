const START = "<!-- arch:summary -->", END = "<!-- /arch:summary -->";
export function replaceSummary(text, block) {
  const start = text.indexOf(START), end = text.indexOf(END);
  if (start < 0 || end < 0 || end < start) throw new Error("README.md has no arch:summary markers");
  return `${text.slice(0, start + START.length)}\n${block.trimEnd()}\n${text.slice(end)}`;
}
