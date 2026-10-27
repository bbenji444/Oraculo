/**
 * Enlace a una página de fuera (la nota original de un medio), que se abre en
 * una pestaña nueva sin tocar el monitor.
 *
 * Por qué no basta `target="_blank"`: en el navegador integrado donde Benji usa
 * el monitor, «Ver nota original» se abría en la misma pestaña y se perdía lo
 * que estaba haciendo (27/10/2026). Al hacer clic normal se abre con
 * `window.open`, que pide una ventana nueva aunque el navegador no respete el
 * `target`. El enlace sigue siendo un `<a>` de verdad: Ctrl+clic, clic con la
 * rueda y «copiar enlace» funcionan como siempre.
 *
 * Lo usan las fichas, la cronología, los casos y el muro. No hace: no abre
 * nada que no sea `http(s)` (las URL de las notas ya se validan en la API).
 */
import type { MouseEvent, ReactNode } from 'react';

interface ExternalLinkProps {
  href: string;
  className?: string;
  title?: string;
  children: ReactNode;
}

export function ExternalLink({ href, className, title, children }: ExternalLinkProps) {
  const open = (event: MouseEvent<HTMLAnchorElement>) => {
    // Con una tecla o con otro botón, el navegador ya sabe qué hacer.
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    window.open(href, '_blank', 'noopener,noreferrer');
  };
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      title={title ?? 'Se abre en una pestaña nueva'}
      onClick={open}
    >
      {children}
    </a>
  );
}
