export function plural(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function alternatives(corrections) {
  return corrections.join(" | ");
}

export function shellWord(text) {
  return /^[\w./:#@-]+$/.test(text) ? text : `'${text}'`;
}
