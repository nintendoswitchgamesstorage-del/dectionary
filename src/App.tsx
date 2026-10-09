import { ArrowRight, Beaker, BookOpen, Bookmark, Check, ChevronDown, CircleHelp, FlaskConical, FolderOpen, Menu, Plus, Save, Sparkles, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, exportProject, post } from './api';
import { AddWord, CandidateDetail, Compare, Modal } from './components';
import Workspace from './Workspace';
import Forge from './Forge';
import Library from './Library';
import Cabinet from './Cabinet';
import type { Analysis, Candidate, Dimension, Project, Root, Source, View } from './types';

const initialConcept = 'Someone who feeds on the work of others, yet mistakes that dependence for power.';
const initialRoots: Root[] = [{ text: 'hunger', language: 'English', meaning: 'an appetite that wants more' }, { text: 'bloom', language: 'English', meaning: 'growth, flowering, unfolding life' }];
const nav: { id: View; label: string; icon: typeof Beaker; note: string }[] = [
  { id: 'workspace', label: 'Concept workspace', icon: Beaker, note: 'Discover & compare' },
  { id: 'forge', label: 'Neologism forge', icon: FlaskConical, note: 'Deform & invent' },
  { id: 'library', label: 'PDF library', icon: BookOpen, note: 'Read & retrieve' },
  { id: 'cabinet', label: 'Saved projects', icon: FolderOpen, note: 'Collect & return' },
];
type Draft = { concept: string; analysis: Analysis | null; candidates: Candidate[]; shortlist: string[]; notes: Record<string, string>; dimensions: Dimension[]; forge_history: Candidate[]; roots: Root[]; id?: string; name?: string };
function readDraft(): Partial<Draft> { try { return JSON.parse(localStorage.getItem('lexical-alchemy-draft') || '{}'); } catch { return {}; } }

export default function App() {
  const [draft] = useState(readDraft);
  const [view, setView] = useState<View>('workspace');
  const [mobileMenu, setMobileMenu] = useState(false);
  const [concept, setConcept] = useState(draft.concept ?? initialConcept);
  const [analysis, setAnalysis] = useState<Analysis | null>(draft.analysis ?? null);
  const [candidates, setCandidates] = useState<Candidate[]>(draft.candidates ?? []);
  const [forgeHistory, setForgeHistory] = useState<Candidate[]>(draft.forge_history ?? []);
  const [roots, setRoots] = useState<Root[]>(draft.roots ?? initialRoots);
  const [shortlist, setShortlist] = useState<string[]>(draft.shortlist ?? []);
  const [notes, setNotes] = useState<Record<string, string>>(draft.notes ?? {});
  const [dimensions, setDimensions] = useState<Dimension[]>(draft.dimensions ?? []);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);
  const [includeWeb, setIncludeWeb] = useState(false);
  const [includeGames, setIncludeGames] = useState(true);
  const [useModel, setUseModel] = useState(false);
  const [modelConfigured, setModelConfigured] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | undefined>(draft.id);
  const [projectName, setProjectName] = useState(draft.name ?? 'An unsettled meaning');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [status, setStatus] = useState<'connecting' | 'ready' | 'offline'>('connecting');
  const [detail, setDetail] = useState<Candidate | null>(null);
  const [compare, setCompare] = useState<Candidate[] | null>(null);
  const [saveModal, setSaveModal] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [help, setHelp] = useState(false);
  const [revise, setRevise] = useState<Candidate | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [method, setMethod] = useState('');

  const notify = useCallback((message: string) => setToast(message), []);
  const onError = useCallback((e: unknown) => setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.'), []);
  const refreshSources = useCallback(async () => { const result = await api<{ sources: Source[] }>('/sources'); setSources(result.sources); }, []);
  const refreshProjects = useCallback(async () => { const result = await api<{ projects: Project[] }>('/projects'); setProjects(result.projects); }, []);

  useEffect(() => {
    let active = true;
    async function start() {
      try {
        await api('/health'); if (!active) return; setStatus('ready');
        await Promise.all([refreshSources(), refreshProjects()]);
        const providers = await api<{ model: { configured: boolean } }>('/providers');
        if (active) setModelConfigured(providers.model.configured);
        if (!draft.candidates?.length) {
          const result = await post<{ candidates: Candidate[]; warnings: string[]; method: string }>('/research', { concept: draft.concept ?? initialConcept, languages: [], source_ids: [], include_web: false, include_games: true, dimensions: [] });
          if (active) { setCandidates(result.candidates); setWarnings(result.warnings ?? []); setMethod(result.method); }
        }
      } catch (e) { if (active) { setStatus('offline'); onError(e); } }
    }
    void start(); return () => { active = false; };
  }, [draft, onError, refreshProjects, refreshSources]);
  useEffect(() => {
    try { localStorage.setItem('lexical-alchemy-draft', JSON.stringify({ concept, analysis, candidates, shortlist, notes, dimensions, forge_history: forgeHistory, roots, id: projectId, name: projectName })); } catch { /* backend project saves are still available when browser storage is full */ }
  }, [concept, analysis, candidates, shortlist, notes, dimensions, forgeHistory, roots, projectId, projectName]);
  useEffect(() => { if (toast) { const timer = window.setTimeout(() => setToast(''), 4500); return () => window.clearTimeout(timer); } }, [toast]);

  const allCandidates = useMemo(() => [...new Map([...candidates, ...forgeHistory].map(c => [c.id, c])).values()], [candidates, forgeHistory]);
  const pinnedCandidates = allCandidates.filter(c => shortlist.includes(c.id));
  function navigate(next: View) { setView(next); setMobileMenu(false); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  function pin(c: Candidate) { setShortlist(s => s.includes(c.id) ? s.filter(id => id !== c.id) : [...s, c.id]); }
  async function research() {
    setBusy('research'); setError('');
    try {
      const result = await post<{ candidates: Candidate[]; warnings: string[]; method: string }>('/research', { concept, interpretation: analysis?.central_meaning, languages: selectedLanguages, source_ids: selectedSources, include_web: includeWeb, include_games: includeGames, dimensions });
      setCandidates(current => [...current.filter(c => shortlist.includes(c.id) || c.source_type === 'user'), ...result.candidates.filter(c => !current.some(item => (shortlist.includes(item.id) || item.source_type === 'user') && item.id === c.id))]); setWarnings(result.warnings ?? []); setMethod(result.method); notify(`${result.candidates.length} candidates found. Read the evidence before choosing.`);
    } catch (e) { onError(e); } finally { setBusy(null); }
  }
  async function analyze() { setBusy('analyze'); setError(''); try { setAnalysis(await post<Analysis>('/analyze', { concept, use_model: useModel })); notify('A provisional reading is ready for your corrections.'); } catch (e) { onError(e); } finally { setBusy(null); } }
  async function generate(level: string) { setBusy('forge'); setError(''); try { const result = await post<{ candidates: Candidate[] }>('/forge', { concept, roots, level, count: 6, use_model: useModel }); setForgeHistory(current => [...result.candidates, ...current.filter(c => shortlist.includes(c.id) && !result.candidates.some(newC => newC.id === c.id))]); notify(`${result.candidates.length} possibilities, with their construction made visible.`); } catch (e) { onError(e); } finally { setBusy(null); } }
  function updateConcept(value: string) { setConcept(value); setAnalysis(null); }
  function toForge(c?: Candidate) { if (c) setRoots([{ text: c.term, language: c.language, meaning: c.definition }, { text: roots[0]?.text === c.term ? 'strange' : roots[0]?.text || 'strange', language: roots[0]?.language || 'English', meaning: roots[0]?.meaning || 'unfamiliar, displaced from ordinary meaning' }]); setDetail(null); navigate('forge'); }
  function addWord(c: Candidate) { setCandidates(current => [c, ...current]); setShortlist(s => [...s, c.id]); notify('Your word has a place in the shortlist.'); }
  function makeProject(): Project { return { id: projectId ?? '', name: projectName.trim() || 'Untitled experiment', concept, analysis, candidates: allCandidates, shortlist, notes, dimensions, forge_history: forgeHistory }; }
  async function save() { setBusy('save'); setError(''); try { const data = makeProject(); const { id, ...body } = data; const result = await post<Project>('/projects', { ...body, ...(id ? { id } : {}) }); setProjectId(result.id); await refreshProjects(); setSaveModal(false); notify('Project saved to your local cabinet.'); } catch (e) { onError(e); } finally { setBusy(null); } }
  async function load(id: string) { setBusy('load'); try { const project = await api<Project>(`/projects/${id}`); setProjectId(project.id); setProjectName(project.name); setConcept(project.concept); setAnalysis(project.analysis ?? null); setCandidates(project.candidates ?? []); setShortlist(project.shortlist ?? []); setNotes(project.notes ?? {}); setDimensions(project.dimensions ?? []); setForgeHistory(project.forge_history ?? []); setWarnings([]); navigate('workspace'); notify(`Reopened “${project.name}”.`); } catch (e) { onError(e); } finally { setBusy(null); } }
  async function deleteProject(id: string) { try { await api(`/projects/${id}`, { method: 'DELETE' }); if (id === projectId) setProjectId(undefined); await refreshProjects(); notify('Saved project removed. Your current draft is still here.'); } catch (e) { onError(e); } }
  async function doExport(format: string) { setBusy('export'); try { await exportProject(format, makeProject()); notify(`${format.toUpperCase()} export created with source notes.`); } catch (e) { onError(e); } finally { setBusy(null); } }
  function newProject() { setProjectId(undefined); setProjectName('Untitled experiment'); setConcept(''); setAnalysis(null); setCandidates([]); setForgeHistory([]); setShortlist([]); setNotes({}); setDimensions([]); setWarnings([]); setMethod(''); navigate('workspace'); notify('A new experiment. Save it when you want to keep it.'); }

  return <div className="app-shell">
    <aside className={`sidebar ${mobileMenu ? 'mobile-open' : ''}`}><a className="brand" href="#" onClick={e => { e.preventDefault(); navigate('workspace'); }}><span className="brand-mark">✳︎</span><span>Lexical<br /><b>Alchemy</b><small>A LANGUAGE LABORATORY</small></span></a><div className="sidebar-rule" /><span className="nav-label">THE LABORATORY</span><nav aria-label="Main navigation">{nav.map(item => <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} aria-current={view === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon size={19} strokeWidth={1.6} /><span>{item.label}<small>{item.note}</small></span>{item.id === 'library' && sources.length > 0 && <span className="nav-count">{sources.length}</span>}{item.id === 'cabinet' && projects.length > 0 && <span className="nav-count">{projects.length}</span>}</button>)}</nav><button className="new-project" onClick={newProject}><Plus size={16} />New experiment</button><div className="sidebar-bottom"><div className="sidebar-manifesto"><span>RIGOROUS WITH EVIDENCE.</span><span>RESTLESS WITH LANGUAGE.</span><div>ἐν ἀρχῇ · 字 · Wort · word</div></div><button className="sidebar-help" onClick={() => setHelp(true)}><CircleHelp size={16} />A note on the laboratory<ArrowRight size={13} /></button><div className="sidebar-status"><span className={`status-dot ${status === 'ready' ? 'green' : status === 'offline' ? 'red' : ''}`} />{status === 'ready' ? 'Local research engine' : status === 'offline' ? 'Backend unavailable' : 'Connecting…'}<span>v0.1</span></div></div></aside>
    {mobileMenu && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMobileMenu(false)} />}
    <div className="main-shell"><header className="topbar"><div className="breadcrumbs"><button className="icon-button mobile-menu-button" aria-label="Open navigation" onClick={() => setMobileMenu(!mobileMenu)}><Menu size={20} /></button><span className="breadcrumb-root">The laboratory</span><span>/</span><b>{nav.find(n => n.id === view)?.label}</b></div><div className="topbar-actions"><button className="shortlist-link" onClick={() => navigate('cabinet')}><Bookmark size={15} /><span>Shortlist</span><b>{shortlist.length}</b></button><span className="topbar-divider" /><button className="button save-top" onClick={() => setSaveModal(true)}><Save size={14} />Save project</button><button className="avatar" onClick={() => setHelp(true)} aria-label="About Lexical Alchemy">LA</button></div></header>
      <main><div className="workspace-status"><span className="eyebrow">WORDS ARE TOOLS. WORDS ARE WORLDS.</span><span><span className="status-dot green" />{useModel ? 'Model assistance' : 'Local mode'}<ChevronDown size={12} /></span></div>{error && <div className="error-banner" role="alert"><span>{status === 'offline' ? 'The research service could not be reached. Start the Python backend on port 8000. ' : ''}{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={17} /></button></div>}
      {view === 'workspace' && <Workspace concept={concept} setConcept={updateConcept} analysis={analysis} setAnalysis={setAnalysis} candidates={candidates} sources={sources} selectedSources={selectedSources} setSelectedSources={setSelectedSources} selectedLanguages={selectedLanguages} setSelectedLanguages={setSelectedLanguages} includeWeb={includeWeb} setIncludeWeb={setIncludeWeb} includeGames={includeGames} setIncludeGames={setIncludeGames} dimensions={dimensions} setDimensions={setDimensions} onAnalyze={() => void analyze()} onResearch={() => void research()} busy={busy} pinned={shortlist} onPin={pin} onDetail={setDetail} onCompare={setCompare} onForge={() => toForge()} onLibrary={() => navigate('library')} warnings={warnings} method={method} useModel={useModel} setUseModel={setUseModel} modelConfigured={modelConfigured} />}
      {view === 'forge' && <Forge concept={concept} setConcept={updateConcept} roots={roots} setRoots={setRoots} candidates={forgeHistory} onGenerate={level => void generate(level)} busy={busy === 'forge'} pinned={shortlist} onPin={pin} onDetail={setDetail} onAdd={() => setAddModal(true)} onRevise={setRevise} useModel={useModel} setUseModel={setUseModel} modelConfigured={modelConfigured} />}
      {view === 'library' && <Library sources={sources} selected={selectedSources} setSelected={setSelectedSources} onRefresh={refreshSources} onError={onError} notify={notify} />}
      {view === 'cabinet' && <Cabinet projects={projects} pinned={pinnedCandidates} notes={notes} onDetail={setDetail} onPin={pin} onNote={(id, value) => setNotes(current => ({ ...current, [id]: value }))} onLoad={id => void load(id)} onDelete={id => void deleteProject(id)} onSave={() => setSaveModal(true)} onExport={format => void doExport(format)} onAdd={() => setAddModal(true)} busy={busy} />}
      <footer className="page-footer"><span>LEXICAL ALCHEMY</span><span>Observed evidence. Open interpretations. New possibilities.</span><span>✳︎</span></footer></main>
    </div>
    {toast && <div className="toast" role="status"><Check size={17} />{toast}<button className="icon-button" onClick={() => setToast('')} aria-label="Dismiss notification"><X size={14} /></button></div>}
    {detail && <CandidateDetail candidate={detail} pinned={shortlist.includes(detail.id)} note={notes[detail.id] ?? ''} onPin={() => pin(detail)} onNote={value => setNotes(current => ({ ...current, [detail.id]: value }))} onForge={() => toForge(detail)} onClose={() => setDetail(null)} />}
    {compare && <Compare candidates={compare} dimensions={dimensions} onClose={() => setCompare(null)} />}
    {addModal && <AddWord onAdd={addWord} onClose={() => setAddModal(false)} />}
    {saveModal && <Modal title="Keep this experiment" onClose={() => setSaveModal(false)}><p className="muted">Save the concept, candidates, annotations, and word families together. Your project stays on this machine.</p><form onSubmit={e => { e.preventDefault(); void save(); }}><label className="field-label" htmlFor="project-name">Project name</label><input id="project-name" value={projectName} onChange={e => setProjectName(e.target.value)} required maxLength={120} /><p className="fine-print">{allCandidates.length} words · {shortlist.length} shortlisted · {Object.keys(notes).filter(id => notes[id]).length} annotations{projectId ? ' · Updates the existing project' : ''}</p><button className="button primary full-width" disabled={busy === 'save' || !projectName.trim()}>{busy === 'save' ? <span className="spinner" /> : <Save size={15} />}Save to cabinet</button></form></Modal>}
    {revise && <Modal title="A word, revised" onClose={() => setRevise(null)}><p className="muted">Keep the original construction and save a new spelling as its own proposed word.</p><form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); const c: Candidate = { ...revise, id: `revision-${crypto.randomUUID()}`, term: String(data.get('term')).trim(), definition: String(data.get('definition')), source_type: 'user', source: { title: `Your revision of ${revise.term}` }, evidence_status: 'coined', caveat: `A user revision of ${revise.term}. Prior usage has not been checked.` }; addWord(c); setForgeHistory(history => [c, ...history]); setRevise(null); }}><label className="field-label" htmlFor="revised-word">Alternate spelling</label><input id="revised-word" name="term" defaultValue={revise.term} required maxLength={100} /><label className="field-label" htmlFor="revised-meaning">Intended meaning</label><textarea id="revised-meaning" name="definition" defaultValue={revise.definition} rows={3} required /><button className="button primary full-width"><Plus size={15} />Save the revision</button></form></Modal>}
    {help && <Modal title="A laboratory for unfinished meanings" onClose={() => setHelp(false)}><div className="help-symbol">✳︎</div><p className="definition-large">Read closely. Invent freely. Keep the difference visible.</p><p>Philologist mode retrieves existing vocabulary from your PDFs and attributed dictionaries. Word-maker mode constructs proposals from the components you choose.</p><h4>What local mode means</h4><p>Concept analysis and relevance ranking use transparent heuristics. The forge uses language transformations. They do not claim model-level understanding or authoritative translation. Optional model configuration is documented in the README.</p><h4>Your sources remain yours</h4><p>PDFs are extracted and indexed on this machine. Live dictionary lookup sends only query terms. Files, indexes, and projects are stored locally; a browser draft is also saved automatically.</p><h4>A label is a promise</h4><p>“Attested” means observed in the cited source. “Unverified” needs checking. “Coined” means proposed here; it does not promise that nobody has used the expression before.</p><button className="button primary full-width" onClick={() => setHelp(false)}><Sparkles size={15} />Back to the experiment</button></Modal>}
  </div>;
}
