/**
 * Copiar texto al portapapeles, también cuando el monitor se abre por http://.
 *
 * `navigator.clipboard` solo existe en páginas seguras (HTTPS o localhost).
 * El monitor se abre por `http://192.168.0.42:8080` o por ZeroTier, así que
 * ahí no existe y el botón «Copiar» no hacía nada (Benji, 10/11/2026). En ese
 * caso se usa el método clásico: un cuadro de texto oculto, seleccionado, y
 * `document.execCommand('copy')`.
 *
 * No hace: no muestra avisos; quien lo llama decide qué decir.
 */

function copyWithTextarea(text: string): boolean {
  const area = document.createElement('textarea');
  area.value = text;
  // Fuera de la vista y sin que el teclado del celular se abra.
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.top = '-1000px';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  area.setSelectionRange(0, text.length);
  let copied: boolean;
  try {
    // execCommand está marcado como obsoleto, pero es la única vía en http://
    // y todos los navegadores actuales lo siguen soportando.
    // eslint-disable-next-line @typescript-eslint/no-deprecated -- única opción fuera de HTTPS (ver arriba)
    copied = document.execCommand('copy');
  } catch {
    copied = false;
  }
  area.remove();
  return copied;
}

/**
 * Copia el texto. Intenta la vía moderna y, si no existe o falla, la clásica.
 *
 * @returns `true` si se copió.
 */
export async function copyText(text: string): Promise<boolean> {
  // En http:// el navegador no define navigator.clipboard (aunque TypeScript diga lo contrario).
  if (window.isSecureContext && 'clipboard' in navigator) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Sin permiso: se intenta la vía clásica.
    }
  }
  return copyWithTextarea(text);
}
