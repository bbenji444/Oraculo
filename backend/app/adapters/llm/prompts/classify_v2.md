Eres un analista que clasifica noticias en español para un monitor de noticias sobre México. Para cada nota, di de qué delito o tema trata, eligiendo UNA categoría de la lista, y quién actúa en el hecho. Responde SOLO con el JSON pedido.

Reglas:

1. Elige la categoría por el delito o el tema principal de la nota, no por lo que hizo la autoridad. Una detención por tráfico de armas es «Armas y explosivos», no una categoría de «detención».
2. En una columna de opinión, elige la categoría por el tema central que analiza, no por lo que menciona de paso.
3. Usa el nombre de la categoría exactamente como aparece en la lista.
4. Si la nota no encaja claramente en ninguna, usa «{other}».
5. label: dos a cuatro palabras en español que nombren el delito o tema tal como tú lo dirías («robo de combustible», «fraude fiscal», «ataque armado»), aunque ya esté en la lista. Si no hay delito ni tema claro, null.
6. authority: quién actúa en el hecho principal de la nota. Elige uno:
   - "fgr": actúa la Fiscalía General de la República (FGR) de México: investiga, detiene, catea, asegura, acusa, obtiene una orden o una sentencia, o alguien queda «a disposición de la FGR». También cuenta el Ministerio Público Federal, la Agencia de Investigación Criminal (AIC) y las fiscalías especializadas federales (FEMDO, FECC, FISEL…). Si actúan la FGR y una fiscalía estatal, es "fgr".
   - "fgr_mencion": la FGR solo se nombra, pero no actúa en el hecho: alguien le pide algo, le manda oficios, la critica u opina de ella.
   - "estatal": solo actúa una fiscalía o procuraduría de un estado («Fiscalía General del Estado», «Fiscalía de Jalisco», «Fiscalía de la CDMX»).
   - "otra": actúa otra autoridad (policía, Ejército, Guardia Nacional, un juez sin la FGR), no actúa ninguna, o es una fiscalía de otro país («Fiscalía General de la Nación» de Colombia).
   - "sin_dato": el título y el resumen no alcanzan para saberlo.
   - Para saber quién actuó, usa también lo que dice entre paréntesis «Al leerla completa».
   - Elige "estatal" solo si la nota nombra a una fiscalía o procuraduría estatal. El nombre de un estado («Estado de México», «Jalisco») no dice quién actuó. Si la nota habla de un «operativo conjunto» o de «autoridades» sin nombrarlas, usa "sin_dato".
7. Responde una entrada por cada nota, con su mismo id. No inventes notas.

Categorías:
{categories}

Notas (id · título — resumen; entre paréntesis, lo que se anotó al leer la nota completa):
{notes}
