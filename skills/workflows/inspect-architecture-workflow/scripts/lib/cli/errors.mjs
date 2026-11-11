export class ArchError extends Error {
  exitCode = 2;
}

export class UsageError extends ArchError {}

export class ModelError extends ArchError {}

export class ToolingError extends ArchError {}
