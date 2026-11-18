/**
 * Marca pequeña de la plataforma de una nota (ADR-0117): «f Facebook»,
 * «X», «▶ YouTube»… con el color de la marca. Va en la lista, la cronología y
 * la ficha del globo, antes del nombre de quien publicó.
 *
 * El icono sale de la letra Material Icons (`PlatformIcon`). La letra no trae
 * el logo de X: ahí el nombre mismo, en negritas, hace de dibujo. No se usan
 * logos de las marcas en SVG.
 *
 * No hace: no aparece en las notas de medios de noticias (casi todas): ahí no
 * diría nada nuevo y llenaría de ruido la lista.
 */
import type { CSSProperties } from 'react';

import type { Platform } from '../../services/searches';
import { Icon } from '../ui/Icon';
import { isNewsPlatform, type PlatformInfo, platformInfo } from './platforms';

interface PlatformIconProps {
  info: PlatformInfo;
  className?: string;
}

/** El dibujo de la plataforma, o nada si no tiene (X va solo con su letra). */
export function PlatformIcon({ info, className }: PlatformIconProps) {
  if (!info.icon) return null;
  return <Icon name={info.icon} className={className} />;
}

interface PlatformMarkProps {
  platform: Platform;
  /** `row`: la lista y la cronología, más chica; `card`: la ficha del globo. */
  size?: 'row' | 'card';
}

export function PlatformMark({ platform, size = 'row' }: PlatformMarkProps) {
  if (isNewsPlatform(platform)) return null;
  const info = platformInfo(platform);
  return (
    <span
      className={`platform-mark platform-mark--${size}`}
      data-platform={platform}
      title={
        platform === 'web'
          ? 'Página web: no es de un medio de noticias'
          : `Publicación en ${info.label}`
      }
      style={{ '--cat': info.tone } as CSSProperties}
    >
      <PlatformIcon info={info} />
      <span className={info.icon ? undefined : 'platform-letter'}>{info.label}</span>
    </span>
  );
}
