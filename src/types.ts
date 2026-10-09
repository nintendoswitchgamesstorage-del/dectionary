export type View = 'workspace' | 'forge' | 'library' | 'cabinet';
export type Evidence = 'attested' | 'historically_attested' | 'specialized' | 'translation_candidate' | 'coined' | 'unverified';
export type Root = { text: string; language: string; meaning: string };
export type Candidate = {
  id: string; term: string; language: string; transliteration?: string;
  definition: string; tone: string; evidence_status: Evidence;
  source_type: 'pdf' | 'dictionary' | 'game' | 'coined' | 'user';
  source: { title: string; url?: string; document_id?: string; filename?: string; page?: number; excerpt?: string; accessed_at?: string };
  fit: number; fit_reason: string; captures: string; misses: string;
  tags?: string[]; components?: Root[]; technique?: string; caveat?: string; etymology?: string;
};
export type Source = { id: string; filename: string; status: string; page_count: number; indexed_pages: number; warning?: string; };
export type Match = { document_id: string; filename: string; page: number; excerpt: string; score: number; };
export type Analysis = { central_meaning: string; tensions: string[]; qualities: string[]; power: string[]; relations: string[]; settings: string[]; distinctions: string[]; method: string; };
export type Dimension = { name: string; weight: number };
export type Project = { id: string; name: string; concept: string; analysis?: Analysis | null; candidates: Candidate[]; shortlist: string[]; notes: Record<string, string>; dimensions: Dimension[]; forge_history?: Candidate[]; updated_at?: string; };

export const evidenceLabels: Record<Evidence, string> = {
  attested: 'Attested', historically_attested: 'Historical', specialized: 'Specialized',
  translation_candidate: 'Translation candidate', coined: 'Coined', unverified: 'Unverified',
};
export const languages = ['English', 'Chinese', 'German', 'Ancient Greek', 'Greek', 'Latin', 'French', 'Russian', 'Persian', 'Azerbaijani'];
