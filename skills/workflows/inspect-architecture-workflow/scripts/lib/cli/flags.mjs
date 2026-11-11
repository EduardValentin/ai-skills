import { UsageError } from "./errors.mjs";

export const GLOBAL_FLAGS = { json: "boolean", record: "value" };

function describeFlags(flags) {
  return Object.keys(flags).map((name) => `--${name}`).join(", ");
}

function checkGitRef(name, value) {
  if (!value.startsWith("-")) return;
  throw new UsageError(
    `--${name} ${value} starts with "-", so git could read it as an option. Pass a branch, tag, or commit name.`,
  );
}

function readFlag(name, kind, argv, index, flags) {
  if (kind === "boolean") {
    flags[name] = true;
    return index;
  }
  const next = argv[index + 1];
  if (next === undefined || next.startsWith("--")) {
    throw new UsageError(`--${name} needs a value. Pass it as --${name} <value>.`);
  }
  if (kind === "git-ref") checkGitRef(name, next);
  flags[name] = kind === "list" ? [...(flags[name] ?? []), next] : next;
  return index + 1;
}

function checkPositionalCount(positional, range, flags) {
  const { min = 0, max = 0 } = range;
  if (positional.length >= min && positional.length <= max) return;
  throw new UsageError(
    `expected ${min} to ${max} positional arguments, got ${positional.length}. Valid flags: ${describeFlags(flags)}.`,
  );
}

export function parseArgs(spec, argv) {
  const flagKinds = { ...spec.flags, ...GLOBAL_FLAGS };
  const positional = [];
  const flags = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      positional.push(arg);
      continue;
    }
    const name = arg.slice(2);
    if (!Object.hasOwn(flagKinds, name)) {
      throw new UsageError(`unknown flag ${arg}. Valid flags: ${describeFlags(flagKinds)}.`);
    }
    index = readFlag(name, flagKinds[name], argv, index, flags);
  }
  checkPositionalCount(positional, spec.positional ?? {}, flagKinds);
  return { positional, flags };
}
