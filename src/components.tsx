import { ArrowUpRight, Bookmark, BookmarkCheck, BookOpen, Check, FlaskConical, Globe2, HelpCircle, Plus, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { Candidate, Evidence } from './types';
import { evidenceLabels } from './types';

export function EvidenceBadge({ status }: { status: Evidence }) {
  return <span className={`evidence evidence-${status}`}><span className="status-dot" />{evidenceLabels[status] ?? status}</span>;
}
export function SourceLink({ candidate, compact = false }: { candidate: Candidate; compact?: boolean }) {
  const source = candidate.source;
  const url = source.document_id ? `/api/sources/${source.document_id}/file#page=${source.page ?? 1}` : source.url;
  const text = compact ? candidate.source_type === 'pdf' ? `PDF · p. ${source.page ?? '—'}` : candidate.source_type === 'coined' ? 'Your experiment' : candidate.source_type === 'game' ? 'Game world' : candidate.source_type === 'user' ? 'Your vocabulary' : 'Dictionary' : `${source.title}${source.page ? ` · p. ${source.page}` : ''}`;
  const icon = candidate.source_type === 'pdf' ? <BookOpen size={13} /> : candidate.source_type === 'coined' ? <FlaskConical size={13} /> : <Globe2 size={13} />;
  return url ? <a className="source-link" href={url} target="_blank" rel="noreferrer">{icon}{text}<ArrowUpRight size={12} /></a> : <span className="source-link">{icon}{text}</span>;
}
export function PinButton({ pinned, onClick, label = '' }: { pinned: boolean; onClick: () => void; label?: string }) {
  return <button className={`icon-button pin-button ${pinned ? 'pinned' : ''}`} onClick={onClick} aria-label={`${pinned ? 'Unpin' : 'Pin'} ${label}`} title={pinned ? 'Remove from shortlist' : 'Pin to shortlist'}>{pinned ? <BookmarkCheck size={18} /> : <Bookmark size={18} />}</button>;
}
export function Empty({ icon = 'flask', title, children }: { icon?: 'flask' | 'book' | 'pin'; title: string; children: React.ReactNode }) {
  return <div className="empty-state"><span className="empty-icon">{icon === 'book' ? <BookOpen size={27} /> : icon === 'pin' ? <Bookmark size={27} /> : <FlaskConical size={27} />}</span><h3>{title}</h3><p>{children}</p></div>;
}
export function Modal({ title, children, onClose, wide = false }: { title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const old = document.activeElement as HTMLElement | null;
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.querySelector<HTMLElement>('button, input, textarea, select, [tabindex]')?.focus();
    function key(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const focusable = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, textarea, select, [tabindex="0"]') ?? []);
        if (!focusable.length) return;
        if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1)?.focus(); }
        else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0].focus(); }
      }
    }
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); document.body.style.overflow = bodyOverflow; old?.focus(); };
  }, [onClose]);
  return <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}><div ref={ref} className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}><div className="modal-heading"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={20} /></button></div>{children}</div></div>;
}
export function CandidateDetail({ candidate, pinned, note, onPin, onNote, onForge, onClose }: { candidate: Candidate; pinned: boolean; note: string; onPin: () => void; onNote: (note: string) => void; onForge: () => void; onClose: () => void }) {
  return <Modal title="A closer reading" onClose={onClose}><div className="detail-title"><div><span className="eyebrow">{candidate.language} {candidate.transliteration && `· ${candidate.transliteration}`}</span><h1>{candidate.term}</h1></div><PinButton pinned={pinned} onClick={onPin} label={candidate.term} /></div><EvidenceBadge status={candidate.evidence_status} /><p className="definition-large">{candidate.definition}</p><div className="detail-grid"><section><h4>What it captures</h4><p>{candidate.captures || candidate.fit_reason}</p></section><section><h4>What it leaves out</h4><p>{candidate.misses || 'Its fit depends on the context and intended audience.'}</p></section></div>{candidate.caveat && <p className="notice"><HelpCircle size={16} />{candidate.caveat}</p>}{candidate.technique && <section className="detail-section"><h4>The construction</h4><p>{candidate.technique}</p><div className="component-chips">{candidate.components?.map((root, i) => <span key={i}><b>{root.text}</b> · {root.language}<small>{root.meaning}</small></span>)}</div></section>}{candidate.etymology && <section className="detail-section"><h4>Etymology from source</h4><p>{candidate.etymology}</p></section>}<section className="detail-section"><h4>Evidence & provenance</h4><SourceLink candidate={candidate} />{candidate.source.excerpt && <blockquote>{candidate.source.excerpt}</blockquote>}{candidate.source.accessed_at && <p className="fine-print">Accessed {candidate.source.accessed_at}</p>}{candidate.source_type === 'pdf' && <p className="fine-print">Found in your document. This confirms the document's usage; it does not independently verify every historical claim.</p>}<p className="fine-print">Fit is an interpretive retrieval estimate, rather than a linguistic fact. {candidate.fit_reason}</p></section><label className="field-label" htmlFor="candidate-note">Your annotation</label><textarea id="candidate-note" value={note} onChange={e => onNote(e.target.value)} placeholder="Where could this word take you?" rows={3} /><div className="modal-actions"><button className="button secondary" onClick={onForge}><FlaskConical size={16} />Take to the forge</button><button className="button primary" onClick={onClose}><Check size={16} />Done</button></div></Modal>;
}
export function Compare({ candidates, dimensions, onClose }: { candidates: Candidate[]; dimensions: { name: string; weight: number }[]; onClose: () => void }) {
  const rows: { label: string; value: (c: Candidate) => React.ReactNode }[] = [{ label: 'Meaning', value: c => c.definition }, { label: 'Evidence', value: c => <EvidenceBadge status={c.evidence_status} /> }, { label: 'Captures', value: c => c.captures }, { label: 'Leaves out', value: c => c.misses }, { label: 'Tone', value: c => c.tone }, { label: 'Source', value: c => <SourceLink candidate={c} /> }, ...dimensions.map(d => ({ label: `${d.name} · weight ${d.weight}`, value: (c: Candidate) => <span>{c.fit_reason}<small className="block fine-print">Review this dimension yourself; the local engine only ranks textual overlap.</small></span> }))];
  return <Modal title="Read them side by side" onClose={onClose} wide><div className="comparison-scroll"><table className="comparison-table"><thead><tr><th>Dimension</th>{candidates.map(c => <th key={c.id}><span className="serif">{c.term}</span><small>{c.language}</small></th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.label}><th>{row.label}</th>{candidates.map(c => <td key={c.id}>{row.value(c)}</td>)}</tr>)}</tbody></table></div></Modal>;
}
export function AddWord({ onAdd, onClose }: { onAdd: (candidate: Candidate) => void; onClose: () => void }) {
  return <Modal title="Add your own word" onClose={onClose}><p className="muted">An invention, a word you overheard, or a root worth following. You can record it without claiming it is attested.</p><form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); const term = String(data.get('term')).trim(); if (!term) return; const isCoined = data.get('evidence') === 'coined'; onAdd({ id: `user-${crypto.randomUUID()}`, term, language: String(data.get('language')), definition: String(data.get('meaning')), tone: 'User supplied', evidence_status: isCoined ? 'coined' : 'unverified', source_type: 'user', source: { title: 'Your vocabulary' }, fit: 0, fit_reason: 'Added by you; not ranked.', captures: String(data.get('meaning')), misses: 'Independent source verification has not been performed.', caveat: isCoined ? 'Proposed in this session; prior usage has not been checked.' : 'A source is needed to verify this term.' }); onClose(); }}><label className="field-label" htmlFor="new-word">Word or expression</label><input id="new-word" name="term" required maxLength={100} autoFocus /><div className="form-two"><div><label className="field-label" htmlFor="new-language">Language</label><input id="new-language" name="language" defaultValue="English" required /></div><div><label className="field-label" htmlFor="new-status">Evidence</label><select id="new-status" name="evidence"><option value="coined">My invention · Coined</option><option value="unverified">Existing word · Unverified</option></select></div></div><label className="field-label" htmlFor="new-meaning">Intended meaning</label><textarea id="new-meaning" name="meaning" required rows={3} /><button className="button primary full-width" type="submit"><Plus size={16} />Add to my shortlist</button></form></Modal>;
}
