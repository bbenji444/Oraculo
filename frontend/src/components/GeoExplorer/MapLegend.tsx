/**
 * Leyenda de las capas de INEGI y en qué zoom aparece cada una.
 */
const ITEMS = [
  { label: 'Países', hint: 'siempre', className: 'border-slate-400' },
  { label: 'Estados', hint: 'al acercarse', className: 'border-sky-400' },
  { label: 'Municipios y alcaldías', hint: 'más cerca', className: 'border-violet-400' },
  {
    label: 'Localidades',
    hint: 'nivel ciudad',
    className: 'rounded-full border-amber-400 bg-amber-400',
  },
];

export function MapLegend() {
  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/85 px-3 py-2.5 text-xs shadow-lg shadow-black/30 backdrop-blur">
      <p className="mb-1.5 font-medium text-slate-300">Capas</p>
      <ul className="space-y-1">
        {ITEMS.map((item) => (
          <li key={item.label} className="flex items-center gap-2 text-slate-400">
            <span aria-hidden="true" className={`size-3 border-2 ${item.className}`} />
            <span className="text-slate-200">{item.label}</span>
            <span className="text-slate-500">· {item.hint}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
