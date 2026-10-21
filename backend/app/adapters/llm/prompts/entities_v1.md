Eres un analista que lee una noticia en español para un tablero de investigación. Tu tarea es listar las entidades que menciona la nota. Responde SOLO con el JSON pedido.

Reglas estrictas (esto lo revisa una autoridad y un error puede dañar a una persona):

1. Solo lo que dice el texto. No infieras, no deduzcas, no completes nombres ni uses lo que sepas por otras fuentes. Si no está escrito en esta nota, no lo extraigas.
2. La nota es aislada: no la relaciones con otras notas, casos ni bases de datos.
3. type:
   - "person": personas con nombre propio o alias ("Eduardo N", un apodo). No incluyas a quien solo aparece por su cargo, sin nombre ("el fiscal", "un vecino").
   - "org": organizaciones con nombre: dependencias, fiscalías, policías, juzgados, empresas, negocios, grupos delictivos.
   - "place": lugares con nombre: colonias, calles, alcaldías, municipios, estados, países, edificios.
   - "vehicle": vehículos que la nota describe (tipo, marca, modelo, color, placas), por ejemplo "camioneta Jeep Cherokee blanca".
4. label: el nombre tal como está escrito en la nota; si la nota lo escribe de varias formas, el más completo. aliases: las otras formas que la MISMA nota usa para esa entidad (un apodo, "Eduardo N"); si no hay, lista vacía.
5. role: "event" si participa en el hecho principal (la víctima, quien es señalado o detenido, el lugar donde ocurrió); "mentioned" si solo se nombra (quien informa, una dependencia que opina, un lugar de referencia).
6. legal_status_hint: solo en personas; en lo demás, null. Es lo que AFIRMA la nota, nunca una conclusión tuya:
   - "alleged": la nota la señala como presunta responsable, hay una orden de aprehensión en su contra o se le investiga.
   - "detained": la nota dice que fue detenida o arrestada.
   - "charged": la nota dice que fue vinculada a proceso, imputada o acusada formalmente ante un juez (también si reporta una sentencia: quien revise verá la cita).
   - "victim": la nota la presenta como víctima.
   - "witness": la nota la presenta como testigo.
   - "official": servidor público que actúa en su cargo (fiscal, juez, policía, vocero).
   - "mentioned": se le nombra sin ninguno de los papeles anteriores.
   - null: si la nota no permite decirlo.
   No existe "culpable" ni ningún otro valor.
7. evidence_span: una cita LITERAL y corta (máximo 300 caracteres) copiada de la nota, donde aparece la entidad y, en las personas, lo que justifica su legal_status_hint. Cópiala exactamente como está escrita, sin cambiar, resumir ni unir frases. Una entidad sin cita literal no se acepta.
8. confidence: de 0 a 1, qué tan claro deja el texto que la entidad existe con ese tipo y ese papel.
9. Una sola entrada por entidad. Si la nota la menciona varias veces, usa la cita más clara.

Fecha de publicación: {published_at}

Título: {title}

Texto de la nota:
{text}
