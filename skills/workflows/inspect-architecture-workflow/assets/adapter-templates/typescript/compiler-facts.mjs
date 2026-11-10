import path from "node:path";

const SCRIPT_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]);

export function isScript(modulePath) {
  return SCRIPT_EXTENSIONS.has(path.extname(modulePath).toLowerCase());
}

function hasModifier(ts, node, kind) {
  const modifiers = ts.canHaveModifiers(node) ? ts.getModifiers(node) ?? [] : [];
  return modifiers.some((modifier) => modifier.kind === kind);
}

function exportedNames(ts, statement) {
  const clause = statement.exportClause;
  return clause && ts.isNamedExports(clause) ? clause.elements.length : 1;
}

function implementedNames(ts, source, statement) {
  const names = [];
  for (const clause of statement.heritageClauses ?? []) {
    if (clause.token !== ts.SyntaxKind.ImplementsKeyword) continue;
    for (const type of clause.types) names.push(type.expression.getText(source));
  }
  return names;
}

function isAbstractExport(ts, statement) {
  if (ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)) return true;
  return ts.isClassDeclaration(statement) && hasModifier(ts, statement, ts.SyntaxKind.AbstractKeyword);
}

export function scanDeclarations(ts, source) {
  const exports = { abstract: 0, concrete: 0 };
  const implemented = [];
  for (const statement of source.statements) {
    if (ts.isExportDeclaration(statement)) {
      exports.concrete += exportedNames(ts, statement);
      continue;
    }
    if (ts.isExportAssignment(statement)) {
      exports.concrete += 1;
      continue;
    }
    if (ts.isClassDeclaration(statement)) implemented.push(...implementedNames(ts, source, statement));
    if (!hasModifier(ts, statement, ts.SyntaxKind.ExportKeyword)) continue;
    if (isAbstractExport(ts, statement)) exports.abstract += 1;
    else if (ts.isVariableStatement(statement)) exports.concrete += statement.declarationList.declarations.length;
    else exports.concrete += 1;
  }
  return { exports, implements: implemented };
}

function uniqueBy(items, key) {
  const seen = new Set();
  return items.filter((item) => {
    if (seen.has(key(item))) return false;
    seen.add(key(item));
    return true;
  });
}

const referenceKey = (reference) => `${reference.symbol}\u0000${reference.path}\u0000${reference.line ?? ""}`;

function relativeModulePath(analysis, fileName) {
  return path.relative(analysis.root, fileName).split(path.sep).join("/");
}

function resolveAlias(ts, checker, symbol) {
  return symbol && symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
}

function moduleReference(analysis, symbol, fromPath) {
  const resolved = resolveAlias(analysis.ts, analysis.checker, symbol);
  const declaration = resolved?.declarations?.[0];
  if (!declaration) return null;
  const declaredIn = relativeModulePath(analysis, declaration.getSourceFile().fileName);
  if (declaredIn === fromPath || !analysis.modules.has(declaredIn)) return null;
  return { symbol: resolved.name, path: declaredIn };
}

function collectNodes(ts, root, collect) {
  const found = [];
  const visit = (node) => {
    const item = collect(node);
    if (item) found.push(item);
    ts.forEachChild(node, visit);
  };
  visit(root);
  return found;
}

function constructedTypes(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const found = collectNodes(ts, source, (node) => {
    if (!ts.isNewExpression(node)) return null;
    return moduleReference(analysis, checker.getSymbolAtLocation(node.expression), filePath);
  });
  return uniqueBy(found, referenceKey);
}

function typeChecks(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const found = collectNodes(ts, source, (node) => {
    if (!ts.isBinaryExpression(node) || node.operatorToken.kind !== ts.SyntaxKind.InstanceOfKeyword) return null;
    const reference = moduleReference(analysis, checker.getSymbolAtLocation(node.right), filePath);
    if (!reference) return null;
    const { line } = source.getLineAndCharacterOfPosition(node.getStart(source));
    return { ...reference, line: line + 1 };
  });
  return uniqueBy(found, referenceKey);
}

function isHidden(ts, member) {
  return hasModifier(ts, member, ts.SyntaxKind.PrivateKeyword)
    || hasModifier(ts, member, ts.SyntaxKind.ProtectedKeyword)
    || (member.name !== undefined && ts.isPrivateIdentifier(member.name));
}

function functionTypeNodes(fn) {
  return [...fn.parameters.map((parameter) => parameter.type), fn.type];
}

function memberTypeNodes(ts, member) {
  if (ts.isConstructorDeclaration(member)) return functionTypeNodes(member);
  if (isHidden(ts, member)) return [];
  if (ts.isFunctionLike(member)) return functionTypeNodes(member);
  if (member.type) return [member.type];
  if (member.initializer && ts.isFunctionLike(member.initializer)) return functionTypeNodes(member.initializer);
  return [];
}

function variableTypeNodes(ts, declaration) {
  const { type, initializer } = declaration;
  if (type) return [type];
  if (initializer && ts.isObjectLiteralExpression(initializer)) {
    return initializer.properties.flatMap((member) => memberTypeNodes(ts, member));
  }
  if (initializer && ts.isFunctionLike(initializer)) return functionTypeNodes(initializer);
  return [];
}

function surfaceTypeNodes(ts, declaration) {
  let nodes = [];
  if (ts.isClassDeclaration(declaration) || ts.isInterfaceDeclaration(declaration)) {
    nodes = declaration.members.flatMap((member) => memberTypeNodes(ts, member));
  } else if (ts.isTypeAliasDeclaration(declaration)) {
    nodes = [declaration.type];
  } else if (ts.isFunctionDeclaration(declaration)) {
    nodes = functionTypeNodes(declaration);
  } else if (ts.isVariableDeclaration(declaration)) {
    nodes = variableTypeNodes(ts, declaration);
  }
  return nodes.filter(Boolean);
}

function referencedTypes(analysis, typeNodes, filePath) {
  const { ts, checker } = analysis;
  const found = typeNodes.flatMap((root) => collectNodes(ts, root, (node) => {
    if (!ts.isTypeReferenceNode(node)) return null;
    return moduleReference(analysis, checker.getSymbolAtLocation(node.typeName), filePath);
  }));
  return uniqueBy(found, referenceKey);
}

function localExports(analysis, source) {
  const { ts, checker } = analysis;
  const moduleSymbol = checker.getSymbolAtLocation(source);
  if (!moduleSymbol) return [];
  return checker.getExportsOfModule(moduleSymbol)
    .filter((symbol) => !(symbol.flags & ts.SymbolFlags.Alias) && symbol.declarations?.length);
}

function exportedValueType(analysis, symbol) {
  const { ts, checker } = analysis;
  if (!(symbol.flags & ts.SymbolFlags.Value)) return null;
  const type = symbol.flags & ts.SymbolFlags.Class
    ? checker.getDeclaredTypeOfSymbol(symbol)
    : checker.getTypeOfSymbolAtLocation(symbol, symbol.declarations[0]);
  return type.flags & ts.TypeFlags.Any ? null : type;
}

function structuralImplements(analysis, exported, filePath) {
  const implemented = [];
  for (const port of analysis.portTypes) {
    if (port.path === filePath) continue;
    const matches = exported.some((symbol) => {
      const type = exportedValueType(analysis, symbol);
      return type !== null && analysis.checker.isTypeAssignableTo(type, port.type);
    });
    if (matches) implemented.push(port.symbol);
  }
  return implemented;
}

function importedNames(ts, statement) {
  if (ts.isExportDeclaration(statement)) {
    const clause = statement.exportClause;
    if (!clause || ts.isNamespaceExport(clause)) return ["*"];
    return clause.elements.map((element) => (element.propertyName ?? element.name).text);
  }
  const clause = statement.importClause;
  if (!clause) return [];
  const names = clause.name ? ["default"] : [];
  const bindings = clause.namedBindings;
  if (bindings && ts.isNamespaceImport(bindings)) names.push("*");
  if (bindings && ts.isNamedImports(bindings)) {
    names.push(...bindings.elements.map((element) => (element.propertyName ?? element.name).text));
  }
  return names;
}

function importedSymbolsByTarget(analysis, source, filePath) {
  const { ts, checker } = analysis;
  const byTarget = new Map();
  for (const statement of source.statements) {
    const isImport = ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement);
    if (!isImport || !statement.moduleSpecifier) continue;
    const target = checker.getSymbolAtLocation(statement.moduleSpecifier)?.declarations?.[0];
    if (!target) continue;
    const targetPath = relativeModulePath(analysis, target.getSourceFile().fileName);
    if (targetPath === filePath || !analysis.modules.has(targetPath)) continue;
    const names = byTarget.get(targetPath) ?? new Set();
    importedNames(ts, statement).forEach((name) => names.add(name));
    byTarget.set(targetPath, names);
  }
  return byTarget;
}

export function scanFacts(analysis, filePath) {
  const source = analysis.program.getSourceFile(path.resolve(analysis.root, filePath));
  if (!source) return null;
  const declared = scanDeclarations(analysis.ts, source);
  const exported = localExports(analysis, source);
  const signatures = exported.map((symbol) => ({
    symbol: symbol.name,
    types: referencedTypes(
      analysis,
      symbol.declarations.flatMap((declaration) => surfaceTypeNodes(analysis.ts, declaration)),
      filePath,
    ),
  }));
  return {
    exports: declared.exports,
    implements: [...new Set([...declared.implements, ...structuralImplements(analysis, exported, filePath)])],
    constructs: constructedTypes(analysis, source, filePath),
    signatures,
    typeChecks: typeChecks(analysis, source, filePath),
    importedSymbols: importedSymbolsByTarget(analysis, source, filePath),
  };
}

export function resolvePortTypes(analysis, ports) {
  const resolved = [];
  for (const port of ports) {
    if (!analysis.modules.has(port.path)) continue;
    const source = analysis.program.getSourceFile(path.resolve(analysis.root, port.path));
    const symbol = source && localExports(analysis, source).find((candidate) => candidate.name === port.symbol);
    if (!symbol) continue;
    const type = analysis.checker.getDeclaredTypeOfSymbol(symbol);
    if (analysis.checker.getPropertiesOfType(type).length > 0) resolved.push({ ...port, type });
  }
  return resolved;
}
