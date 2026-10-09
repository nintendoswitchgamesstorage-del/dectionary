import { ArrowUpRight, BookOpen, Check, FileText, Loader2, RefreshCw, Search, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { api, post } from './api';
import { Empty } from './components';
import type { Match, Source } from './types';

export default function Library({ sources, selected, setSelected, onRefresh, onError, notify }: { sources: Source[]; selected: string[]; setSelected: (ids: string[]) => void; onRefresh: () => Promise<void>; onError: (error: unknown) => void; notify: (message: string) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [uploadWarnings, setUploadWarnings] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null);
  async function upload(files: FileList | File[]) {
    if (!files.length) return;
    setBusy('upload');
    try {
      const data = new FormData();
      for (const file of Array.from(files)) { if (!file.name.toLowerCase().endsWith('.pdf')) throw new Error('Please choose PDF files.'); data.append('files', file); }
      const result = await api<{ uploaded: Source[]; warnings: string[] }>('/sources', { method: 'POST', body: data });
      setUploadWarnings(result.warnings ?? []);
      await onRefresh(); setMatches(null); notify(`${result.uploaded.length} document${result.uploaded.length === 1 ? '' : 's'} processed. Check their indexing status below.`);
    } catch (e) { onError(e); } finally { setBusy(null); if (input.current) input.current.value = ''; }
  }
  async function search() {
    setBusy('search');
    try { const result = await api<{ matches: Match[] }>(`/sources/search?q=${encodeURIComponent(query)}${selected.length ? `&source_ids=${selected.map(encodeURIComponent).join(',')}` : ''}`); setMatches(result.matches); } catch (e) { onError(e); } finally { setBusy(null); }
  }
  async function remove(id: string) {
    setBusy(id); try { await api(`/sources/${id}`, { method: 'DELETE' }); setSelected(selected.filter(s => s !== id)); await onRefresh(); setMatches(null); notify('Document and its search index removed.'); } catch (e) { onError(e); } finally { setBusy(null); setConfirmRemove(null); }
  }
  async function reprocess(id: string) { setBusy(id); try { await post(`/sources/${id}/reprocess`, {}); await onRefresh(); notify('Document reprocessed.'); } catch (e) { onError(e); } finally { setBusy(null); } }
  return <>
    <div className="page-intro"><div><span className="eyebrow orange">THE SOURCE LIBRARY</span><h1>Your reading becomes <em>raw material.</em></h1><p>A private, page-aware collection of books, essays, and unlikely connections.</p></div><span className="intro-icon"><BookOpen size={52} strokeWidth={1} /></span></div>
    <div className="library-summary"><span><b>{sources.length}</b> documents</span><span><b>{sources.reduce((sum, source) => sum + source.indexed_pages, 0).toLocaleString()}</b> searchable pages</span><span><ShieldCheck size={15} />Processed on this machine</span></div>
    <div className="upload-zone" role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click(); } }} onClick={() => { if (!busy) input.current?.click(); }} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) void upload(e.dataTransfer.files); }} aria-label="Upload PDF documents"><span className="upload-icon">{busy === 'upload' ? <Loader2 className="spin" size={26} /> : <Upload size={26} />}</span><h3>{busy === 'upload' ? 'Extracting and indexing your pages…' : 'Bring another voice into the laboratory.'}</h3><p>Drop PDFs here, or <span>browse your files</span>. Multiple documents welcome.</p><small>Local text extraction · Page citations retained · Duplicate detection</small></div><input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={e => { if (e.target.files) void upload(e.target.files); }} aria-label="PDF files" />
    {!!uploadWarnings.length && <div className="upload-warnings" role="status">{uploadWarnings.map((warning, i) => <p className="notice" key={i}>{warning}</p>)}</div>}<div className="results-heading library-heading"><div><span className="eyebrow">YOUR COLLECTION</span><h2>Read, indexed, ready to explore.</h2></div><span className="fine-print">Select documents to narrow both library search and concept research.</span></div><div className="document-list">{sources.length ? sources.map(source => <article className="document-card card" key={source.id}><label className="document-select"><input type="checkbox" aria-label={`Select ${source.filename}`} checked={selected.includes(source.id)} onChange={e => setSelected(e.target.checked ? [...selected, source.id] : selected.filter(id => id !== source.id))} /></label><span className="document-icon"><FileText size={24} strokeWidth={1.3} /></span><div className="document-info"><a href={`/api/sources/${source.id}/file`} target="_blank" rel="noreferrer">{source.filename}<ArrowUpRight size={13} /></a><p>{source.page_count} pages · {source.indexed_pages} searchable · {source.status === 'ready' || source.status === 'indexed' ? <span className="success-text"><Check size={12} />Indexed</span> : <span className="warning-text">{source.status.replaceAll('_', ' ')}</span>}</p>{source.warning && <p className="warning-text document-warning">{source.warning}</p>}</div><div className="document-actions">{confirmRemove === source.id ? <><span className="fine-print">Remove file & index?</span><button className="button danger small-button" disabled={!!busy} onClick={() => void remove(source.id)}>Remove</button><button className="text-button" onClick={() => setConfirmRemove(null)}>Cancel</button></> : <><button className="icon-button" aria-label={`Reprocess ${source.filename}`} title="Reprocess document" disabled={!!busy} onClick={() => void reprocess(source.id)}><RefreshCw size={16} className={busy === source.id ? 'spin' : ''} /></button><button className="icon-button" aria-label={`Remove ${source.filename}`} title="Remove document" disabled={!!busy} onClick={() => setConfirmRemove(source.id)}><Trash2 size={16} /></button></>}</div></article>) : <Empty icon="book" title="A library begins with one document">Upload your first PDF. Scanned files will show an OCR notice if they contain no searchable text.</Empty>}</div>
    <section className="pdf-search card"><div className="section-kicker"><Search size={17} /><h2>Search within the pages</h2><span className="tiny-label">{selected.length ? `${selected.length} SELECTED` : 'ALL DOCUMENTS'}</span></div><form className="inline-form" onSubmit={e => { e.preventDefault(); void search(); }}><input aria-label="Search PDF text" value={query} onChange={e => setQuery(e.target.value)} placeholder="A word, phrase, or conceptual thread…" required maxLength={300} /><button className="button primary" disabled={!!busy || !query.trim()}>{busy === 'search' ? <span className="spinner" /> : <Search size={16} />}Search pages</button></form><p className="fine-print">Exact phrase and related word-form retrieval. Local search does not claim human-level semantic understanding.</p>{matches !== null && <div className="pdf-matches"><p className="small-label">{matches.length} matching passages</p>{matches.length ? matches.map((match, index) => <article key={`${match.document_id}-${match.page}-${index}`} className="pdf-match"><div><FileText size={15} /><b>{match.filename}</b><a href={`/api/sources/${match.document_id}/file#page=${match.page}`} target="_blank" rel="noreferrer">Page {match.page}<ArrowUpRight size={13} /></a></div><blockquote>{match.excerpt}</blockquote></article>) : <p className="muted">No matching text found. Try fewer words or broaden your document selection.</p>}</div>}</section>
    <p className="privacy-note"><ShieldCheck size={17} /><span>Your PDFs and extracted text stay in the local <code>.data</code> folder. No document contents are sent to dictionaries. Image-only pages are reported and need optional local OCR.</span></p>
  </>;
}
