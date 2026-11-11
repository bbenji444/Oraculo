/**
 * Pestañas del detalle de un caso (F12, ADR-0107): Panorama, Entidades,
 * Vínculos y Noticias.
 *
 * Antes las tres secciones iban una debajo de otra y había que bajar mucho
 * para llegar a los vínculos. Ahora se ve una a la vez y cada pestaña dice
 * cuánto queda por revisar («Entidades · 12 por revisar»), para saber dónde
 * hace falta trabajo sin abrirlas. Abre en el Panorama: quién está en el
 * caso y con quién se relaciona.
 *
 * También vigila la lectura de la IA: cuando termina, vuelve a pedir
 * duplicados y vínculos aunque se esté viendo otra pestaña.
 *
 * No hace: no revisa nada (eso es cada sección).
 */
import { useState } from 'react';

import { useCaseEntities, useRefreshWhenAnalysisEnds } from '../../hooks/useEntities';
import { useCaseRelationships } from '../../hooks/useRelationships';
import { CaseArticles } from './CaseArticles';
import { CaseEntities } from './CaseEntities';
import { CaseOverview } from './CaseOverview';
import { CaseRelationships } from './CaseRelationships';

export type CaseSection = 'overview' | 'entities' | 'relationships' | 'articles';

interface CaseSectionsProps {
  caseId: string;
  articleCount: number;
  /** Puede revisar y quitar: editor o dueño, con el caso abierto. */
  canEdit: boolean;
}

/** «12 por revisar» al lado del nombre de la pestaña; nada si no queda. */
function Pending({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span className="ml-1.5 rounded-full border border-amber-300/40 bg-amber-300/10 px-1.5 py-0.5 text-[10px] tracking-normal text-amber-100 normal-case">
      {count} por revisar
    </span>
  );
}

export function CaseSections({ caseId, articleCount, canEdit }: CaseSectionsProps) {
  const [section, setSection] = useState<CaseSection>('overview');
  // Las mismas consultas que usan las pestañas: TanStack Query no las repite.
  const entities = useCaseEntities(caseId, 'suggested').data;
  const relationships = useCaseRelationships(caseId, 'suggested').data;
  useRefreshWhenAnalysisEnds(caseId, entities?.analysis.queued ?? 0);

  const tabs: { value: CaseSection; label: string; pending: number }[] = [
    { value: 'overview', label: 'Panorama', pending: 0 },
    { value: 'entities', label: 'Entidades', pending: entities?.counts.suggested ?? 0 },
    { value: 'relationships', label: 'Vínculos', pending: relationships?.counts.suggested ?? 0 },
    { value: 'articles', label: `Noticias (${String(articleCount)})`, pending: 0 },
  ];

  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label="Partes del caso"
        className="hud-panel flex flex-wrap gap-1 px-3"
      >
        {tabs.map((t) => (
          <button
            key={t.value}
            id={`caso-tab-${t.value}`}
            type="button"
            role="tab"
            aria-selected={section === t.value}
            aria-controls={`caso-panel-${t.value}`}
            onClick={() => {
              setSection(t.value);
            }}
            className="hud-subtab focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            {t.label}
            {/* Solo quien puede revisar necesita el aviso. */}
            {canEdit && <Pending count={t.pending} />}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`caso-panel-${section}`} aria-labelledby={`caso-tab-${section}`}>
        {section === 'overview' && (
          <CaseOverview caseId={caseId} canEdit={canEdit} onNavigate={setSection} />
        )}
        {section === 'entities' && <CaseEntities caseId={caseId} canEdit={canEdit} />}
        {section === 'relationships' && <CaseRelationships caseId={caseId} canEdit={canEdit} />}
        {section === 'articles' && (
          <CaseArticles caseId={caseId} articleCount={articleCount} canEdit={canEdit} />
        )}
      </div>
    </div>
  );
}
