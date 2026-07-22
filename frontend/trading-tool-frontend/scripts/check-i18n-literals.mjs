import fs from "fs";
import path from "path";
import ts from "typescript";

const ROOT = process.cwd();
const TARGET_DIRS = ["app", "components"];
const CORE_PREFIXES = [
  "app/",
  "components/",
];
const EXTENSIONS = new Set([".js", ".jsx", ".ts", ".tsx"]);
const IGNORE_FILES = new Set([
  "app/providers/I18nProvider.tsx",
  // Retained only for the explicit legacy variant; the 3.0 workspace has its own translated UI.
  "components/workflows/MarketAnalysisWorkflow.jsx",
]);

const IGNORE_PREFIXES = [
  "components/modal/",
  "components/auth/",
];

const findings = [];

function walk(dir, results = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "out" || entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      walk(fullPath, results);
      continue;
    }
    if (EXTENSIONS.has(path.extname(entry.name))) results.push(fullPath);
  }
  return results;
}

function isLikelyUserFacing(text) {
  const value = text.trim();
  if (!value) return false;
  if (value.length < 4) return false;
  if (!/[A-Za-zÀ-ÿ]/.test(value)) return false;
  if (/^(use client|https?:|[A-Z0-9_./:-]+)$/.test(value)) return false;
  if (/^(bg-|text-|border-|px-|py-|mx-|my-|mt-|mb-|w-|h-|flex|grid|rounded|shadow|transition)/.test(value)) return false;
  return /\s/.test(value) || /[a-z][A-Z]/.test(value);
}

function isAllowed(node, sourceFile) {
  const parent = node.parent;
  if (!parent) return false;

  if (ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent)) return true;
  if (ts.isExpressionStatement(parent) && ts.isStringLiteral(node)) return true;
  if (ts.isBinaryExpression(parent) && ["||", "??"].includes(parent.operatorToken.getText(sourceFile))) return true;
  if (ts.isJsxAttribute(parent)) {
    const name = parent.name.getText(sourceFile);
    if (["className", "href", "src", "alt", "id", "key", "type", "role", "rel", "target", "viewBox"].includes(name)) {
      return true;
    }
  }
  if (ts.isPropertyAssignment(parent)) {
    const name = parent.name.getText(sourceFile);
    if (["event_name", "page", "surface", "flow_type", "metric", "timeframe", "symbol", "href"].includes(name)) {
      return true;
    }
  }
  if (ts.isCallExpression(parent)) {
    const expression = parent.expression.getText(sourceFile);
    if (expression.includes("console.") || expression === "require" || expression.includes("trackAssistantEvent")) {
      return true;
    }
  }

  return false;
}

function isUserFacingAttribute(node, sourceFile) {
  if (!ts.isJsxAttribute(node)) return false;
  const name = node.name.getText(sourceFile);
  return [
    "title",
    "placeholder",
    "label",
    "helperText",
    "aria-label",
  ].includes(name);
}

function isUserFacingProperty(node, sourceFile) {
  if (!ts.isPropertyAssignment(node)) return false;
  const name = node.name.getText(sourceFile);
  return [
    "title",
    "subtitle",
    "description",
    "label",
    "placeholder",
    "helperText",
    "confirmText",
    "cancelText",
    "statusLabel",
    "context",
    "impact",
    "safety",
    "consequence",
    "emptyHint",
  ].includes(name);
}

function checkFile(filePath) {
  const relativePath = path.relative(ROOT, filePath);
  if (IGNORE_FILES.has(relativePath)) return;
  if (!CORE_PREFIXES.some((prefix) => relativePath.startsWith(prefix))) return;
  if (IGNORE_PREFIXES.some((prefix) => relativePath.startsWith(prefix))) return;

  const sourceText = fs.readFileSync(filePath, "utf8");
  const sourceFile = ts.createSourceFile(filePath, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  function visit(node) {
    if (ts.isJsxText(node)) {
      const text = node.getText(sourceFile).replace(/\s+/g, " ").trim();
      if (isLikelyUserFacing(text)) {
        findings.push(`${relativePath}:${sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1} JSX text "${text}"`);
      }
    }

    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const text = node.text;
      const parent = node.parent;
      const shouldCheck =
        isUserFacingAttribute(parent, sourceFile) ||
        isUserFacingProperty(parent, sourceFile);

      if (shouldCheck && isLikelyUserFacing(text) && !isAllowed(node, sourceFile)) {
        findings.push(`${relativePath}:${sourceFile.getLineAndCharacterOfPosition(node.getStart()).line + 1} string "${text}"`);
      }
    }

    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
}

for (const dir of TARGET_DIRS) {
  walk(path.join(ROOT, dir)).forEach(checkFile);
}

if (findings.length > 0) {
  console.error("Hardcoded user-facing strings found:\n");
  for (const finding of findings) {
    console.error(`- ${finding}`);
  }
  process.exit(1);
}

console.log("No suspicious hardcoded UI strings found.");
