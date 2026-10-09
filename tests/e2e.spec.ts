import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const run = `E2E-${Date.now()}-${randomBytes(4).toString('hex')}`;
const marker = `lexicaltest${randomBytes(6).toString('hex')}`;
const firstName = `${run}-first.pdf`;
const secondName = `${run}-second.pdf`;
const projectName = `${run}-cabinet`;
let fixtureDirectory = '';
let firstFile = '';
let secondFile = '';

/** Build a real, tiny text PDF with page-specific content and a valid xref. */
function pdf(pages: string[]): Buffer {
  const objects: string[] = [];
  const pageIds = pages.map((_, index) => 3 + index * 2);
  const fontId = 3 + pages.length * 2;
  objects.push('<< /Type /Catalog /Pages 2 0 R >>');
  objects.push(`<< /Type /Pages /Count ${pages.length} /Kids [${pageIds.map(id => `${id} 0 R`).join(' ')}] >>`);
  for (let index = 0; index < pages.length; index++) {
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 ${fontId} 0 R >> >> /Contents ${pageIds[index] + 1} 0 R >>`);
    const text = pages[index].replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)');
    const stream = `BT /F1 12 Tf 40 740 Td (${text}) Tj ET\n`;
    objects.push(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}endstream`);
  }
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  let body = '%PDF-1.4\n';
  const offsets = [0];
  for (let index = 0; index < objects.length; index++) {
    offsets.push(Buffer.byteLength(body));
    body += `${index + 1} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xref = Buffer.byteLength(body);
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body);
}

async function cleanOwnArtifacts(request: APIRequestContext) {
  // Prefixes are cryptographically unique to this run. Existing user data is
  // never removed, even when a test fails halfway through an upload or save.
  const sourcesResponse = await request.get('/api/sources');
  if (sourcesResponse.ok()) {
    const { sources } = await sourcesResponse.json() as { sources: { id: string; filename: string }[] };
    for (const source of sources.filter(item => item.filename.startsWith(run))) {
      await request.delete(`/api/sources/${encodeURIComponent(source.id)}`);
    }
  }
  const projectsResponse = await request.get('/api/projects');
  if (projectsResponse.ok()) {
    const { projects } = await projectsResponse.json() as { projects: { id: string; name: string }[] };
    for (const project of projects.filter(item => item.name === projectName)) {
      await request.delete(`/api/projects/${encodeURIComponent(project.id)}`);
    }
  }
}

async function navigate(page: Page, name: string) {
  await page.getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name: new RegExp(`^${name}\\b`) }).click();
}

test.beforeAll(async () => {
  fixtureDirectory = await mkdtemp(join(tmpdir(), 'lexical-alchemy-e2e-'));
  firstFile = join(fixtureDirectory, firstName);
  secondFile = join(fixtureDirectory, secondName);
  await writeFile(firstFile, pdf([
    'Ordinary language is a cabinet for thoughts. This is the introductory page.',
    `${marker} means a hunger that grows with everything it consumes. Memory, power, and dependence become raw material.`,
  ]));
  await writeFile(secondFile, pdf([
    `${marker} describes a strange ecology, a world that feeds on its makers. Hunger changes the creature and its environment.`,
    'A different page considers ordinary vocabulary and its transformation.',
  ]));
});

test.afterAll(async ({ request }) => {
  try { await cleanOwnArtifacts(request); }
  finally { if (fixtureDirectory) await rm(fixtureDirectory, { recursive: true, force: true }); }
});

test('concept interpretation, real research, filtering, comparison and source details', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Describe a concept').fill('A hunger that consumes others and feeds on their work, yet mistakes dependence for power.');
  await page.getByRole('button', { name: 'Interpret', exact: true }).click();
  await expect(page.getByLabel('What do you mean, precisely?')).toBeVisible();
  await page.getByLabel('What do you mean, precisely?').fill('A parasitic hunger for power that depends on another person’s work.');
  await page.getByRole('button', { name: 'Research settings', exact: true }).click();
  await page.getByLabel('Try live dictionary lookup').uncheck();
  await page.getByRole('button', { name: 'Explore the concept', exact: true }).click();
  const rows = page.locator('.candidate-table tbody tr');
  await expect(rows.first()).toBeVisible();
  await expect(page.locator('.candidate-table .evidence').first()).toHaveText(/Attested|Historical|Specialized|Translation candidate|Unverified/);

  await page.getByLabel('Filter evidence status').selectOption('attested');
  const visibleBadges = page.locator('.candidate-table tbody .evidence');
  await expect(visibleBadges.first()).toBeVisible();
  for (const status of await visibleBadges.allTextContents()) expect(status.trim()).toBe('Attested');
  await page.getByLabel('Filter evidence status').selectOption('coined');
  await expect(page.getByRole('heading', { name: 'No words in this selection' })).toBeVisible();
  await expect(rows).toHaveCount(0);
  await page.getByLabel('Filter evidence status').selectOption('all');
  await page.getByLabel('Sort candidates').selectOption('term');
  const firstTerm = (await rows.first().locator('.term-button').innerText()).trim();
  await page.getByLabel('Filter candidates').fill(firstTerm);
  await expect(rows.first().locator('.term-button')).toHaveText(firstTerm);
  await page.getByRole('button', { name: firstTerm, exact: true }).first().click();
  const detail = page.getByRole('dialog', { name: 'A closer reading' });
  await expect(detail.getByRole('heading', { name: 'Evidence & provenance', exact: true })).toBeVisible();
  await expect(detail.locator('.source-link')).toBeVisible();
  await expect(detail.getByText(/Fit is an interpretive retrieval estimate/)).toBeVisible();
  await detail.getByRole('button', { name: 'Close dialog' }).click();
  await page.getByLabel('Filter candidates').fill('');
  await rows.nth(0).getByRole('checkbox').check();
  await rows.nth(1).getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Compare side by side' }).click();
  await expect(page.getByRole('dialog', { name: 'Read them side by side' }).locator('.comparison-table')).toBeVisible();
});

test('multiple PDFs index locally and expose exact document/page citations', async ({ page, request }) => {
  await page.goto('/');
  await navigate(page, 'PDF library');
  await page.getByLabel('PDF files').setInputFiles([firstFile, secondFile]);
  const firstCard = page.locator('.document-card').filter({ hasText: firstName });
  const secondCard = page.locator('.document-card').filter({ hasText: secondName });
  await expect(firstCard).toContainText('2 pages');
  await expect(firstCard).toContainText('2 searchable');
  await expect(secondCard).toContainText('Indexed');
  await page.getByLabel('Search PDF text').fill(marker);
  await page.getByRole('button', { name: 'Search pages', exact: true }).click();
  const matches = page.locator('.pdf-match');
  await expect(matches).toHaveCount(2);
  const firstMatch = matches.filter({ hasText: firstName });
  const secondMatch = matches.filter({ hasText: secondName });
  await expect(firstMatch.getByRole('link', { name: 'Page 2' })).toHaveAttribute('href', /#page=2$/);
  await expect(secondMatch.getByRole('link', { name: 'Page 1' })).toHaveAttribute('href', /#page=1$/);
  await expect(firstMatch.locator('blockquote')).toContainText(marker);
  await expect(secondMatch.locator('blockquote')).toContainText(marker);

  await page.getByLabel(`Select ${firstName}`).check();
  await page.getByRole('button', { name: 'Search pages', exact: true }).click();
  await expect(matches).toHaveCount(1);
  await expect(matches.first()).toContainText(firstName);
  await page.getByRole('button', { name: `Reprocess ${firstName}`, exact: true }).click();
  await expect(firstCard).toContainText('Indexed');
  await expect(page.getByRole('button', { name: `Reprocess ${firstName}`, exact: true })).toBeEnabled();

  await navigate(page, 'Concept workspace');
  await page.getByLabel('Describe a concept').fill(marker);
  await page.getByRole('button', { name: 'Explore the concept', exact: true }).click();
  await page.getByLabel('Filter source').selectOption('pdf');
  const row = page.locator('.candidate-table tbody tr').first();
  await expect(row).toBeVisible();
  await expect(row.locator('.source-link')).toContainText('p. 2');
  await expect(row.locator('.source-link')).toHaveAttribute('href', /#page=2$/);
  await row.locator('.term-button').click();
  const detail = page.getByRole('dialog', { name: 'A closer reading' });
  await expect(detail.locator('.source-link')).toContainText(firstName);
  await expect(detail.locator('blockquote')).toContainText(marker);
  await detail.getByRole('button', { name: 'Close dialog' }).click();

  await navigate(page, 'PDF library');
  await page.getByRole('button', { name: `Remove ${secondName}`, exact: true }).click();
  await secondCard.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(secondCard).toHaveCount(0);
  const response = await request.get('/api/sources');
  const { sources } = await response.json() as { sources: { filename: string }[] };
  expect(sources.some(source => source.filename === secondName)).toBe(false);
});

test('Unicode forge proposals can be pinned, annotated, saved, reopened and exported', async ({ page, request }) => {
  await page.goto('/');
  await navigate(page, 'Neologism forge');
  await page.getByLabel('Root 1', { exact: true }).fill('梦');
  await page.getByLabel('Root 1 language', { exact: true }).fill('Chinese');
  await page.getByLabel('Root 1 meaning', { exact: true }).fill('dream, a supplied experimental gloss');
  await page.getByLabel('Root 2', { exact: true }).fill('θάλασσα');
  await page.getByLabel('Root 2 language', { exact: true }).fill('Greek');
  await page.getByLabel('Root 2 meaning', { exact: true }).fill('sea, a supplied experimental gloss');
  await page.getByRole('button', { name: 'Forge new possibilities', exact: true }).click();
  const cards = page.locator('.coinage-card');
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeGreaterThan(3);
  for (const status of await cards.locator('.evidence').allTextContents()) expect(status.trim()).toBe('Coined');
  const selectedCard = cards.first();
  const term = (await selectedCard.locator('.coinage-term').innerText()).trim();
  await selectedCard.getByRole('button', { name: `Pin ${term}`, exact: true }).click();
  await expect(selectedCard.getByRole('button', { name: `Unpin ${term}`, exact: true })).toBeVisible();
  await selectedCard.getByRole('button', { name: 'Read the construction' }).click();
  let detail = page.getByRole('dialog', { name: 'A closer reading' });
  await expect(detail.getByRole('heading', { name: 'The construction', exact: true })).toBeVisible();
  await expect(detail).toContainText('prior use has not been checked');
  await expect(detail).toContainText('Native-speaker and grammar review');
  const note = 'Keep the seam visible: this is a proposal, not an attested Greek or Chinese word.';
  await detail.getByLabel('Your annotation').fill(note);
  await detail.getByRole('button', { name: 'Done', exact: true }).click();

  // Changing the level must change actual constructions and retain pinned
  // members of the earlier word family, rather than only relabeling a batch.
  await page.getByRole('button', { name: /Radical$/ }).click();
  await page.getByRole('button', { name: 'Forge new possibilities', exact: true }).click();
  await expect(cards).toHaveCount(7);
  expect((await cards.locator('.coinage-term').allTextContents()).some(text => /[↯∴]/.test(text))).toBe(true);
  await page.getByRole('button', { name: `Revise ${term}`, exact: true }).click();
  const revision = page.getByRole('dialog', { name: 'A word, revised' });
  const alternate = `${term}~`;
  await revision.getByLabel('Alternate spelling', { exact: true }).fill(alternate);
  await revision.getByRole('button', { name: 'Save the revision', exact: true }).click();
  await expect(page.getByRole('button', { name: `Unpin ${alternate}`, exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Save project', exact: true }).click();
  const saveDialog = page.getByRole('dialog');
  await saveDialog.getByLabel('Project name', { exact: true }).fill(projectName);
  const saving = page.waitForResponse(response => response.url().endsWith('/api/projects') && response.request().method() === 'POST');
  await saveDialog.getByRole('button', { name: 'Save to cabinet', exact: true }).click();
  await saving;
  await expect(saveDialog).toBeHidden();
  const projectsResponse = await request.get('/api/projects');
  const { projects } = await projectsResponse.json() as { projects: { id: string; name: string; notes: Record<string, string>; candidates: { term: string; evidence_status: string }[]; shortlist: string[] }[] };
  const saved = projects.find(project => project.name === projectName);
  expect(saved).toBeDefined();
  expect(Object.values(saved!.notes)).toContain(note);
  expect(saved!.shortlist.length).toBeGreaterThan(0);
  expect(saved!.candidates.some(candidate => candidate.term === term && candidate.evidence_status === 'coined')).toBe(true);
  expect(saved!.candidates.some(candidate => candidate.term === alternate && candidate.evidence_status === 'coined')).toBe(true);

  // Discard this test browser's automatic draft: reopening must actually restore
  // the backend project, not merely reveal the same state left in localStorage.
  await page.evaluate(() => localStorage.removeItem('lexical-alchemy-draft'));
  await page.reload();
  await navigate(page, 'Saved projects');
  const projectCard = page.locator('.project-card').filter({ hasText: projectName });
  await expect(projectCard).toBeVisible();
  await projectCard.getByRole('button', { name: /Open|Continue|Reopen/ }).click();
  await expect(page.getByRole('button', { name: term, exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: term, exact: true }).first().click();
  detail = page.getByRole('dialog', { name: 'A closer reading' });
  await expect(detail.getByLabel('Your annotation')).toHaveValue(note);
  await detail.getByRole('button', { name: 'Done', exact: true }).click();
  await navigate(page, 'Saved projects');

  for (const format of ['Markdown', 'CSV', 'PDF']) {
    const downloading = page.waitForEvent('download');
    await page.getByRole('button', { name: format, exact: true }).click();
    const download = await downloading;
    expect(await download.failure()).toBeNull();
    const file = await download.path();
    expect(file).not.toBeNull();
    const bytes = await readFile(file!);
    expect(bytes.length).toBeGreaterThan(100);
    if (format === 'PDF') {
      expect(bytes.subarray(0, 5).toString()).toBe('%PDF-');
      const pdfText = execFileSync(process.env.LEXICAL_TEST_PYTHON || 'python', [
        '-c', 'import fitz,sys; doc=fitz.open(sys.argv[1]); print("\\n".join(page.get_text() for page in doc))', file!,
      ], { encoding: 'utf8' }).replace(/\s+/g, ' ');
      expect(pdfText).toContain(term);
      expect(pdfText).toMatch(/coined/i);
      expect(pdfText).toContain(note);
    }
    else {
      expect(bytes.toString('utf8')).toContain(term);
      expect(bytes.toString('utf8')).toMatch(/coined/i);
      expect(bytes.toString('utf8')).toContain(note);
    }
  }
});
