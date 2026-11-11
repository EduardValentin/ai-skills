export function plural(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function alternatives(corrections) {
  return corrections.join(" | ");
}
