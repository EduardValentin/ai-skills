function typeOf(value) {
  if (Array.isArray(value)) return "array";
  if (value === null) return "null";
  return typeof value;
}

function matchesType(value, type) {
  const actual = typeOf(value);
  if (type === "integer") return Number.isInteger(value);
  return actual === type;
}

function checkType(value, schema, path) {
  if (!schema.type) return [];
  const types = [].concat(schema.type);
  if (types.some((type) => matchesType(value, type))) return [];
  return [`${path}: expected ${types.join(" or ")}, got ${typeOf(value)}`];
}

function checkEnum(value, schema, path) {
  if (!schema.enum || schema.enum.includes(value)) return [];
  return [`${path}: must be one of ${schema.enum.join(", ")}, got ${JSON.stringify(value)}`];
}

function checkString(value, schema, path) {
  if (typeof value !== "string") return [];
  if (schema.minLength && value.length < schema.minLength) return [`${path}: must not be empty`];
  if (schema.pattern && !new RegExp(schema.pattern).test(value)) return [`${path}: must match ${schema.pattern}`];
  return [];
}

function checkNumber(value, schema, path) {
  if (typeof value !== "number") return [];
  const problems = [];
  const { minimum, maximum } = schema;
  if (minimum !== undefined && value < minimum) problems.push(`${path}: must be at least ${minimum}`);
  if (maximum !== undefined && value > maximum) problems.push(`${path}: must be at most ${maximum}`);
  if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) {
    problems.push(`${path}: must be greater than ${schema.exclusiveMinimum}`);
  }
  return problems;
}

function checkArray(value, schema, path) {
  if (!Array.isArray(value)) return [];
  const problems = [];
  if (schema.minItems !== undefined && value.length < schema.minItems) {
    problems.push(`${path}: needs at least ${schema.minItems} items`);
  }
  if (schema.maxItems !== undefined && value.length > schema.maxItems) {
    problems.push(`${path}: allows at most ${schema.maxItems} items`);
  }
  value.forEach((item, index) => {
    const itemSchema = schema.prefixItems?.[index] ?? schema.items;
    if (itemSchema) problems.push(...validateShape(item, itemSchema, `${path}[${index}]`));
  });
  return problems;
}

function checkObject(value, schema, path) {
  if (typeOf(value) !== "object") return [];
  const problems = [];
  for (const key of schema.required ?? []) {
    if (!Object.hasOwn(value, key)) problems.push(`${path ? `${path}.` : ""}${key}: is required`);
  }
  for (const [key, child] of Object.entries(value)) {
    const childPath = path ? `${path}.${key}` : key;
    const childSchema = schema.properties?.[key] ?? schema.additionalProperties;
    if (childSchema === false) problems.push(`${childPath}: is not a known field`);
    else if (childSchema && childSchema !== true) problems.push(...validateShape(child, childSchema, childPath));
  }
  return problems;
}

export function validateShape(value, schema, path = "") {
  const typeProblems = checkType(value, schema, path || "model");
  if (typeProblems.length > 0) return typeProblems;
  return [
    ...checkEnum(value, schema, path),
    ...checkString(value, schema, path),
    ...checkNumber(value, schema, path),
    ...checkArray(value, schema, path),
    ...checkObject(value, schema, path),
  ];
}
