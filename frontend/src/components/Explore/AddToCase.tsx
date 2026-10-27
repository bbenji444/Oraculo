/**
 * «Agregar al caso» en la ficha de una noticia (Fase 9.3, historia H9.1).
 *
 * - Si hay un último caso usado y abierto, un solo botón la agrega ahí
 *   («Agregar a «Homicidio…»»): 8 notas seguidas, 8 clics.
 * - «▾ Otro caso» abre la lista de mis casos abiertos, con ✓ en los que ya la
 *   tienen, y «Nuevo caso…» para crear uno y agregarla en el mismo paso.
 *
 * Agregar dos veces no duplica nada (lo garantiza la API). Solo se ofrecen
 * casos abiertos: los cerrados no admiten notas hasta reabrirlos.
 *
 * No hace: no quita notas (eso está en la sección Casos).
 */
import { useState } from 'react';

import { useAddCaseArticle, useCasesForArticle, useCreateCase } from '../../hooks/useCases';
import type { Case } from '../../services/cases';
import { useExplorerStore } from '../../store/explorer';
import { withLastFirst } from './caseOrder';

/** "1 nota", "8 notas". */
function notesLabel(count: number): string {
  return `${String(count)} ${count === 1 ? 'nota' : 'notas'}`;
}

interface AddToCaseProps {
  articleId: number;
}

const ROW =
  'flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-all duration-300 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-default';

export function AddToCase({ articleId }: AddToCaseProps) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const cases = useCasesForArticle(articleId);
  const add = useAddCaseArticle();
  const create = useCreateCase();
  const lastCaseId = useExplorerStore((s) => s.lastCaseId);
  const setLastCaseId = useExplorerStore((s) => s.setLastCaseId);
  const ordered = withLastFirst(cases.data ?? [], lastCaseId);
  const last = ordered.find((c) => c.id === lastCaseId);
  const inCases = ordered.filter((c) => c.has_article);
  const busy = add.isPending || create.isPending;
  const error = add.error ?? create.error;

  function addTo(target: Case) {
    add.mutate(
      { caseId: target.id, articleId },
      {
        onSuccess: (added) => {
          setLastCaseId(target.id);
          setNotice(added ? `Agregada a «${target.name}».` : `Ya estaba en «${target.name}».`);
          setOpen(false);
        },
      },
    );
  }

  function createAndAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!newName?.trim()) return;
    create.mutate(
      { name: newName, description: '', sensitivity: 'normal' },
      {
        onSuccess: (created) => {
          setNewName(null);
          addTo(created);
        },
      },
    );
  }

  return (
    <div className="space-y-2 border-t border-white/10 pt-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {last && !last.has_article ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              addTo(last);
            }}
            className="hud-btn hud-btn--sm max-w-full truncate border-emerald-400/50 text-emerald-100"
          >
            + Agregar a «{last.name}»
          </button>
        ) : null}
        <button
          type="button"
          aria-expanded={open}
          onClick={() => {
            setOpen(!open);
            setNotice(null);
          }}
          className="hud-btn hud-btn--sm"
        >
          {last && !last.has_article ? '▾ Otro caso' : '+ Agregar al caso'}
        </button>
        {inCases.length > 0 && (
          <span className="text-[11px] text-emerald-200/90">
            ✓ En{' '}
            {inCases.length === 1
              ? `«${inCases[0]?.name ?? ''}»`
              : `${String(inCases.length)} casos`}
          </span>
        )}
      </div>

      {open && (
        <div
          role="group"
          aria-label="Elegir caso"
          className="hud-reveal space-y-1 rounded-xl border border-sky-400/25 bg-[#050d12]/95 p-1.5 shadow-lg shadow-black/50"
        >
          {cases.isPending && <p className="px-2 py-1 text-xs text-slate-400">Cargando casos…</p>}
          {cases.isSuccess && ordered.length === 0 && (
            <p className="px-2 py-1 text-xs text-slate-400">No tienes casos abiertos.</p>
          )}
          {ordered.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={busy || item.has_article === true}
              onClick={() => {
                addTo(item);
              }}
              className={`${ROW} ${item.has_article ? 'text-slate-400' : 'text-slate-100 hover:translate-x-0.5 hover:bg-sky-400/10'}`}
            >
              <span className="truncate">{item.name}</span>
              <span className="shrink-0 text-[11px]">
                {item.has_article ? '✓ ya está' : notesLabel(item.article_count)}
              </span>
            </button>
          ))}
          {newName === null ? (
            <button
              type="button"
              onClick={() => {
                setNewName('');
              }}
              className={`${ROW} text-sky-200 hover:translate-x-0.5 hover:bg-sky-400/10`}
            >
              + Nuevo caso…
            </button>
          ) : (
            <form onSubmit={createAndAdd} className="flex gap-1.5 px-1 py-1">
              <input
                aria-label="Nombre del caso nuevo"
                value={newName}
                onChange={(event) => {
                  setNewName(event.target.value);
                }}
                placeholder="Nombre del caso"
                className="hud-input min-w-0 flex-1 px-2 py-1 text-xs"
              />
              <button
                type="submit"
                disabled={busy || !newName.trim()}
                className="hud-btn hud-btn--solid hud-btn--sm"
              >
                Crear y agregar
              </button>
            </form>
          )}
        </div>
      )}

      <p aria-live="polite" className="text-[11px]">
        {notice && <span className="text-emerald-200">{notice}</span>}
        {error && <span className="text-rose-300">{error.message}</span>}
      </p>
    </div>
  );
}
