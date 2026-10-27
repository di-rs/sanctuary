// Exercise the same extraction and replacement code used by the pinned Renovate runtime.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
assert(process.argv[2], 'Pass the installed Renovate package directory');
const moduleAt = (name) => import(pathToFileURL(resolve(process.argv[2], `dist/${name}.js`)));
const { init } = await moduleAt('logger/index');
await init();
const { GlobalConfig } = await moduleAt('config/global');
const { regexEngineStatus } = await moduleAt('util/regex');
assert.equal(regexEngineStatus.type, 'available', 'Tests require the real RE2 engine');
const { extractPackageFile: extractCustom } = await moduleAt('modules/manager/custom/regex/index');
const { get: versioning } = await moduleAt('modules/versioning/index');
const { doAutoReplace } = await moduleAt('workers/repository/update/branch/auto-replace');
const config = JSON.parse(readFileSync('renovate.json', 'utf8'));
const files = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
  encoding: 'utf8',
}).trim().split('\n');
const read = (file) => readFileSync(resolve(root, file), 'utf8');
const dependencies = [];
const scratch = mkdtempSync(resolve(tmpdir(), 'sanctuary-renovate-'));
try {
  GlobalConfig.set({ localDir: scratch });
  for (const manager of config.customManagers) {
    let count = 0;
    for (const file of files.filter((file) => manager.managerFilePatterns.some(
      (pattern) => new RegExp(pattern.slice(1, -1)).test(file),
    ))) {
      const content = read(file);
      const result = extractCustom(content, file, manager);
      for (const [depIndex, dep] of (result?.deps ?? []).entries()) {
        assert(!dep.skipReason, `${file}: ${dep.depName} skipped: ${dep.skipReason}`);
        assert(versioning(dep.versioning).isValid(dep.currentValue),
          `Unparseable version: ${dep.depName} ${dep.currentValue}`);
        dependencies.push({ ...dep, file });
        // Change both version and digest, then let Renovate re-extract its replacement.
        const newValue = dep.currentValue.replace(/\d+/, '999');
        const newDigest = dep.currentDigest?.replace(/[a-f0-9]{64}$/, 'a'.repeat(64));
        const changed = await doAutoReplace({
          ...manager, ...dep, manager: 'regex', packageFile: file, depIndex,
          newValue, newDigest, autoReplaceGlobalMatch: true,
        }, content, false);
        assert(changed && changed !== content, `No replacement for ${file}: ${dep.depName}`);
        assert.equal(changed.split(dep.replaceString).length, content.split(dep.replaceString).length - 1,
          `Expected one occurrence to be updated: ${file}: ${dep.depName}`);
        if (file.endsWith('.json')) {
          const inventory = JSON.parse(changed);
          const records = [...Object.values(inventory.images ?? inventory), inventory.collector].filter(Boolean);
          for (const record of records) {
            const image = record.image ?? record.source_image;
            if (image) assert(image.includes(`:${record.version}@sha256:`), `Version/image drift: ${image}`);
          }
          const plugin = inventory.plugins?.['victoriametrics-logs-datasource'];
          if (plugin) {
            assert(plugin.url.includes(`/download/${plugin.version}/`));
            assert(plugin.url.endsWith(`/victoriametrics-logs-datasource-${plugin.version}.zip`));
          }
        }
        count++;
      }
    }
    assert(count > 0, `Custom manager matched nothing: ${manager.description}`);
    console.log(`${manager.description} ${count} pins extracted and updated.`);
  }
  GlobalConfig.set({ localDir: root });
  for (const name of ['docker-compose', 'dockerfile', 'github-actions', 'cargo', 'pep621', 'npm', 'rust-toolchain', 'pyenv', 'nodenv']) {
    const manager = await moduleAt(`modules/manager/${name}/index`);
    let count = 0;
    for (const file of files.filter((file) => manager.defaultConfig.managerFilePatterns.some(
      (pattern) => new RegExp(pattern.slice(1, -1)).test(file),
    ))) {
      const extractor = name === 'npm' ? await moduleAt('modules/manager/npm/extract/index') : manager;
      const result = await extractor.extractPackageFile(read(file), file, {});
      for (const dep of result?.deps ?? []) {
        dependencies.push({ ...dep, file, manager: name });
        if (dep.depType === 'action') assert(!dep.skipReason, `${file}: untracked action ${dep.depName}`);
        if (!dep.skipReason) count++;
      }
    }
    assert(count > 0, `Built-in manager matched no dependencies: ${name}`);
    console.log(`${name}: ${count} dependencies extracted.`);
  }
  for (const file of files.filter((file) => /^\.github\/workflows\/.*\.yml$/.test(file))) {
    for (const match of read(file).matchAll(/tool: ([^\n]+)/g)) {
      for (const tool of match[1].split(',')) {
        assert(dependencies.some((dep) => dep.file === file && dep.replaceString === tool),
          `Untracked installed tool: ${file}: ${tool}`);
      }
    }
  }
  for (const file of ['packages/boxie/infra/observability/versions.json',
    'packages/boxie/infra/temporal/versions.json']) {
    const inventory = JSON.parse(read(file));
    const images = Object.values(inventory.images ?? inventory).map((record) => record.image);
    images.push(inventory.collector?.source_image, inventory.collector?.base);
    for (const image of images.filter(Boolean)) {
      assert(dependencies.some((dep) => dep.file === file && dep.replaceString.includes(image)),
        `Untracked inventory image: ${file}: ${image}`);
    }
  }
  // Every inventory image must also be found by the actual Compose/Dockerfile managers.
  for (const dep of dependencies.filter((dep) => dep.file.endsWith('/versions.json') && dep.datasource === 'docker')) {
    const consumers = dependencies.filter((other) => other.manager && other.depName === dep.depName);
    assert(consumers.length > 0, `No consuming manifest for ${dep.depName}`);
    for (const consumer of consumers) {
      assert.equal(consumer.currentValue, dep.currentValue, `${consumer.file}: version drift`);
      assert.equal(consumer.currentDigest, dep.currentDigest, `${consumer.file}: digest drift`);
    }
  }
  for (const required of ['docker.io/cloudflare/cloudflared', 'temporalio/server', 'temporalio/admin-tools',
    'temporalio/ui', 'VictoriaMetrics/victorialogs-datasource', 'lycheeverse/lychee', 'rhysd/actionlint',
    'pulumi/pulumi', 'gitleaks/gitleaks', 'renovate']) {
    assert(dependencies.some((dep) => (dep.packageName ?? dep.depName) === required && !dep.skipReason),
      `Missing dependency: ${required}`);
  }
  if (process.argv.includes('--verify-assets')) {
    const verified = new Set();
    for (const dep of dependencies.filter((dep) => dep.datasource === 'github-release-attachments')) {
      const tag = dep.currentValue;
      const asset = {
        'lycheeverse/lychee': 'lychee-x86_64-unknown-linux-musl.tar.gz',
        'rhysd/actionlint': `actionlint_${tag.replace(/^v/, '')}_linux_amd64.tar.gz`,
        'VictoriaMetrics/victorialogs-datasource': `victoriametrics-logs-datasource-${tag}.zip`,
      }[dep.depName];
      assert(asset, `Add checksum validation for ${dep.depName}`);
      const url = `https://github.com/${dep.depName}/releases/download/${tag}/${asset}`;
      const key = `${url} ${dep.currentDigest}`;
      if (verified.has(key)) continue;
      const response = await fetch(url, { signal: AbortSignal.timeout(120_000) });
      assert(response.ok && response.body, `Download failed: ${url}: ${response.status}`);
      const hash = createHash('sha256');
      let bytes = 0;
      for await (const chunk of response.body) {
        bytes += chunk.length;
        assert(bytes <= 128 * 1024 * 1024, `Release asset exceeds 128 MiB: ${url}`);
        hash.update(chunk);
      }
      assert.equal(hash.digest('hex'), dep.currentDigest, `Release checksum mismatch: ${url}`);
      verified.add(key);
    }
    console.log(`${verified.size} release asset checksums verified against downloaded bytes.`);
  }
  console.log('Dependency coverage, replacement, and image consistency checks passed.');
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
