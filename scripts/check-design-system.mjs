import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const sourceRoot = path.join(projectRoot, 'src');
const tokenFile = path.join(sourceRoot, 'styles', 'tokens.css');
const typographyFile = path.join(sourceRoot, 'styles', 'typography.css');
const shadcnRoot = path.join(sourceRoot, 'components', 'ui');
const supportedExtensions = new Set([
  '.css',
  '.js',
  '.jsx',
  '.mjs',
  '.ts',
  '.tsx',
]);

const violations = [];

async function collectFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(
    entries.map(async (entry) => {
      const entryPath = path.join(directory, entry.name);

      if (entry.isDirectory()) {
        return collectFiles(entryPath);
      }

      return supportedExtensions.has(path.extname(entry.name))
        ? [entryPath]
        : [];
    }),
  );

  return files.flat();
}

function relativePath(file) {
  return path.relative(projectRoot, file);
}

function lineNumberAt(content, index) {
  return content.slice(0, index).split('\n').length;
}

function report(file, content, index, message) {
  violations.push(
    `${relativePath(file)}:${lineNumberAt(content, index)} ${message}`,
  );
}

function checkRawColors(file, content) {
  if (file === tokenFile) return;

  for (const match of content.matchAll(/#[\da-f]{3,8}\b/gi)) {
    report(
      file,
      content,
      match.index,
      `raw color ${match[0]} must use a token`,
    );
  }
}

function checkArbitraryClasses(file, content) {
  if (file.startsWith(`${shadcnRoot}${path.sep}`)) return;

  const arbitraryDesignClass =
    /\b(?:font|leading|tracking|text|p[trblxy]?|m[trblxy]?|gap(?:-[xy])?|space-[xy]|rounded(?:-[trbl]{1,2})?)-\[[^\]]+\]/g;
  const nonSemanticTextSize = /\btext-(?:xs|sm|base|lg|xl|[2-9]xl)\b/g;
  const unsupportedFontWeight =
    /\bfont-(?:thin|extralight|light|bold|extrabold|black)\b/g;

  for (const match of content.matchAll(arbitraryDesignClass)) {
    report(
      file,
      content,
      match.index,
      `arbitrary design class ${match[0]} is forbidden`,
    );
  }

  for (const match of content.matchAll(nonSemanticTextSize)) {
    report(
      file,
      content,
      match.index,
      `font-size class ${match[0]} must use a type-* role`,
    );
  }

  for (const match of content.matchAll(unsupportedFontWeight)) {
    report(
      file,
      content,
      match.index,
      `font-weight class ${match[0]} is outside weights 400, 500, and 600`,
    );
  }

  if (path.extname(file) === '.css') return;

  const approvedSpacingSteps = new Set([
    '0',
    '1',
    '2',
    '3',
    '4',
    '6',
    '8',
    '10',
    '12',
    '16',
    '20',
  ]);
  const numericSpacingClass =
    /\b(?:p[trblxy]?|m[trblxy]?|gap(?:-[xy])?|space-[xy])-(-?\d+(?:\.\d+)?)\b/g;

  for (const match of content.matchAll(numericSpacingClass)) {
    if (!approvedSpacingSteps.has(match[1])) {
      report(
        file,
        content,
        match.index,
        `spacing class ${match[0]} is outside the approved scale`,
      );
    }
  }
}

function checkPrimitiveImports(file, content) {
  const relative = path.relative(sourceRoot, file);
  const isRouteOrFeature =
    relative.startsWith(`app${path.sep}`) ||
    relative.startsWith(`features${path.sep}`);

  if (!isRouteOrFeature) return;

  const imports = /(?:from\s+|import\s*)['"]([^'"]+)['"]/g;

  for (const match of content.matchAll(imports)) {
    if (match[1].startsWith('@/components/ui')) {
      report(
        file,
        content,
        match.index,
        `route and feature code must consume an Orion wrapper, not ${match[1]}`,
      );
    }
  }
}

function checkCssTypography(file, content) {
  if (path.extname(file) !== '.css' || file === typographyFile) return;

  const declaration =
    /(?:font-size|font-weight|line-height|letter-spacing)\s*:\s*([^;\n]+)/g;

  for (const match of content.matchAll(declaration)) {
    report(
      file,
      content,
      match.index,
      `typography declarations belong in ${relativePath(typographyFile)}`,
    );
  }
}

function featureName(file) {
  const relative = path.relative(path.join(sourceRoot, 'features'), file);

  if (relative.startsWith('..')) return undefined;

  return relative.split(path.sep)[0];
}

function checkFeatureImports(file, content) {
  const sourceFeature = featureName(file);
  if (!sourceFeature) return;

  const imports = /(?:from\s+|import\s*)['"]([^'"]+)['"]/g;

  for (const match of content.matchAll(imports)) {
    const specifier = match[1];
    const aliasMatch = specifier.match(/^@\/features\/([^/]+)(\/.+)?$/);

    if (aliasMatch) {
      const [, targetFeature, privatePath] = aliasMatch;
      if (targetFeature !== sourceFeature && privatePath) {
        report(
          file,
          content,
          match.index,
          `import ${specifier} bypasses ${targetFeature}'s public index`,
        );
      }
      continue;
    }

    if (!specifier.startsWith('.')) continue;

    const resolved = path.resolve(path.dirname(file), specifier);
    const targetFeature = featureName(resolved);
    if (targetFeature && targetFeature !== sourceFeature) {
      report(
        file,
        content,
        match.index,
        `relative import ${specifier} crosses into feature ${targetFeature}`,
      );
    }
  }
}

function checkDuplicateComponentNames(filesWithContent) {
  const declarations = new Map();
  const componentDeclaration =
    /(?:export\s+)?(?:default\s+)?function\s+([A-Z][\w]*)\b|(?:export\s+)?const\s+([A-Z][\w]*)\s*=/g;

  for (const { file, content } of filesWithContent) {
    if (
      path.extname(file) !== '.tsx' ||
      /\.(?:test|spec)\.tsx$/.test(file) ||
      file.startsWith(`${shadcnRoot}${path.sep}`)
    ) {
      continue;
    }

    for (const match of content.matchAll(componentDeclaration)) {
      const name = match[1] ?? match[2];
      const declaration = { file, content, index: match.index };
      const existing = declarations.get(name);

      if (existing) {
        report(
          file,
          content,
          match.index,
          `component ${name} duplicates ${relativePath(existing.file)}:${lineNumberAt(existing.content, existing.index)}`,
        );
      } else {
        declarations.set(name, declaration);
      }
    }
  }
}

const files = await collectFiles(sourceRoot);
const filesWithContent = await Promise.all(
  files.map(async (file) => ({ file, content: await readFile(file, 'utf8') })),
);

for (const { file, content } of filesWithContent) {
  checkRawColors(file, content);
  checkArbitraryClasses(file, content);
  checkCssTypography(file, content);
  checkFeatureImports(file, content);
  checkPrimitiveImports(file, content);
}

checkDuplicateComponentNames(filesWithContent);

if (violations.length > 0) {
  console.error('Design-system policy violations:\n');
  console.error(violations.map((violation) => `- ${violation}`).join('\n'));
  process.exitCode = 1;
} else {
  console.log('Design-system policy checks passed.');
}
