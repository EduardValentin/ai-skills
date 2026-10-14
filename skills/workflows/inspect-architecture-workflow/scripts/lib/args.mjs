const BOOLEAN_FLAGS = new Set(["json", "force", "with-neighbors", "one-off", "standing"]);

export function parseFlags(args) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (!arg.startsWith("--")) { positional.push(arg); continue; }
    const key = arg.slice(2);
    const next = args[i + 1];
    if (BOOLEAN_FLAGS.has(key) || next === undefined || next.startsWith("--")) { flags[key] = true; continue; }
    flags[key] = next;
    i += 1;
  }
  return { positional, flags };
}

export function savedInputs(flags) {
  return { cruiseJsonPath: flags["cruise-json"], factsJsonPath: flags["facts-json"] ?? flags["exports-json"] };
}
