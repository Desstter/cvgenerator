# Selección, evaluación y mejora

## Evaluación de la oferta

Primero revisa condiciones excluyentes de la campaña: país desde el que se permite trabajar, ciudad presencial, modalidad, antigüedad máxima, disponibilidad, contrato y salario cuando está publicado. Registra las incógnitas y resuelve las que afecten la elegibilidad o exijan un compromiso. Cuando no se publica salario, `unknown_salary_action: "review"` indica revisar la oferta normalmente. Aplica cualquier límite salarial explícito cuando haya evidencia comparable.

Conserva dos edades cuando difieran: fecha original en la descripción y fecha/republicación indicada por la plataforma. Para la campaña Colombia/Cali, los valores de ejemplo priorizan 7 días y aceptan hasta 14; otras campañas pueden cambiarlos. No confundas publicaciones antiguas con ofertas nuevas por su posición en la búsqueda.

Emite un `job_assessment.json` junto al snapshot, con este contenido:

```json
{
  "source_url": "https://example.com/jobs/123",
  "decision": "shortlist",
  "score": 78,
  "dimensions": {
    "mandatory_requirements": {"score": 32, "max": 40, "evidence": ["..."]},
    "responsibilities": {"score": 24, "max": 30, "evidence": ["..."]},
    "preferences": {"score": 7, "max": 10, "evidence": ["..."]},
    "conditions": {"score": 15, "max": 20, "evidence": ["..."]}
  },
  "hard_blocks": [],
  "gaps": ["..."],
  "unknowns": ["..."],
  "salary": {
    "source": "not_published",
    "published_range": null,
    "currency": null,
    "period": null,
    "contract_type": null,
    "candidate_expectation": null
  },
  "reason": "..."
}
```

La nota es una rúbrica orientativa del agente y debe justificarse con la oferta y el perfil; no es una probabilidad de conseguir entrevista. Separa los requisitos por función: condiciones de elegibilidad (país, autorización, horario o contrato), capacidades centrales del trabajo y herramientas concretas. Marca un `hard_block` solo ante una condición real de elegibilidad que falla, una licencia/credencial exigida legalmente para ejercer la función, o una capacidad central que el candidato no puede desempeñar. **La falta de un título universitario/profesional en Ingeniería o carrera afín casi nunca es por sí sola un bloqueo para este candidato, incluso cuando la oferta lo llame “indispensable”: si el trabajo encaja, sigue y permite que el empleador valore la equivalencia.** Nunca falsifiques un título; declara su formación técnica real y contesta con veracidad los filtros de formación. Si una respuesta veraz impide técnicamente el envío, registra ese impedimento concreto. Una tecnología enumerada como ejemplo, preferida o aprendible no es por sí sola un bloqueo.

Evalúa el trabajo que la persona ya sabe hacer y su experiencia transferible antes de penalizar una herramienta desconocida. Por ejemplo, la falta de un lenguaje concreto no descarta automáticamente a quien domina otro lenguaje pertinente; la falta de un constructor visual no invalida experiencia real construyendo y manteniendo sitios WordPress; y la experiencia con herramientas de marketing relacionadas puede respaldar una candidatura sin afirmar que conoce todo el stack. Registra la brecha con precisión, pero no conviertas un requisito deseable o una herramienta sustituible en un rechazo automático. Solo presenta como dominio las herramientas verificadas; no inventes experiencia para mejorar el encaje.

Usa el umbral configurado para priorizar, explicando qué responsabilidades sí cubre la experiencia demostrada y qué requisitos específicos quedan por aprender o verificar. Puedes proponer candidaturas con brechas no excluyentes. No elimines una condición de elegibilidad verdaderamente excluyente por sumar puntos en otros aspectos.

## Salario y costos

Distingue salario publicado, expectativa de negociación y remuneración actual o histórica. Para estas últimas usa un dato verificado y autorizado, o una opción de declinar que el portal acepte. Una estimación nunca demuestra cuánto gana o ganó la persona.

### Expectativa salarial delegada

Una expectativa verificada y aplicable en `application_answers.salary_expectation` tiene prioridad. Una instrucción explícita de la petición actual puede sustituirla. Si no hay cifra aplicable y `application_answers.salary_policy.mode` es `hire_first`, decide la propuesta siguiendo estos pasos.

1. Si el formulario ofrece «Negociable» o admite texto, indica que la expectativa es negociable según el alcance del puesto y la compensación total, en el idioma del formulario. Si el campo pide un mínimo firme para aceptar una oferta, usa únicamente el mínimo autorizado o deja la decisión abierta con una opción válida. La delegación cubre propuestas de negociación.
2. Si exige cifra, usa el rango publicado para esa vacante o el importe fijo anunciado. Con un rango, parte del primer cuartil (`mínimo + 0,25 × (máximo − mínimo)`). Elige una cifra redondeada en la parte baja compatible con el campo, el rango y los mínimos aplicables. Si exige un rango, usa la mitad inferior cuando sea compatible. Si el piso está por encima de la mitad, elige la cifra o intervalo admisible más bajo que aún quepa en el rango de referencia. Para un desplegable, compara las opciones por valor y elige la más cercana al objetivo que cumpla los límites.
3. Sin salario publicado, consulta referencias recientes para puestos comparables por país del contrato, nivel, horario y tipo de contratación. Usa dos referencias independientes cuando existan y conserva sus enlaces, fechas y comparabilidad. Si solo hay una referencia reciente, úsala únicamente si publica un rango con comparabilidad clara. Aplica el mismo criterio al rango respaldado. Si ni la publicación ni la evidencia de mercado sostienen una cifra, registra esa limitación y continúa con otra oferta.
4. Aplica `criteria.minimum_salary` y `application_answers.salary_policy.minimum` cuando sean pertinentes. Si ambos aplican, respeta el mayor. Normaliza moneda, período, tipo de remuneración y modalidad de contrato antes de comparar. Una cifra mensual bruta y una tarifa por hora en otro contrato no son directamente comparables. Verifica las conversiones necesarias con una fuente actual y confirma el sentido de un símbolo ambiguo como `$` en el propio formulario. Si el presupuesto publicado resulta incompatible con el mínimo, registra la incompatibilidad.

`salary_policy.minimum` es `null` cuando el candidato no configuró un piso específico para la propuesta. Si se configura, usa un objeto con `value`, `currency`, `period` y, cuando corresponda, `basis` (bruto/neto) y `contract_type`. El modo `verified_only` o la ausencia de `salary_policy` mantiene el comportamiento de usar una cifra verificada o dejarla abierta cuando esté autorizado. Evita cifras simbólicas y remuneraciones supuestas. Para cada decisión delegada guarda pregunta, importe o texto, moneda, período, fuentes, criterio y la etiqueta `delegated` en la carpeta de la oferta. Reutilízala en esa oferta si permanecen iguales la pregunta, las unidades y las condiciones. Conserva su carácter de propuesta.

Registra como costos del proceso el proveedor/modelo, si hubo refinamiento y el número de generaciones. Usa datos reales de uso y tarifas verificadas para informar un costo exacto. Si un portal exige pagar, registra el motivo y sigue con otras ofertas.

## Evaluación del CV

Comprueba la atribución de cada logro al empleador concreto. No conviertas un proyecto personal en experiencia de una empresa por similitud de tecnologías. Si el candidato confirma el vínculo, registra el hecho y su fuente en `experience_context` de esa empresa antes de generar. `excluded_projects` elimina del CV los proyectos indicados por nombre o URL; los CV históricos que todavía los mencionen deben revisarse antes de volver a usarse.

Crea `cv_assessment_<record_id>.json` después de `inspect` y actualízalo para la versión revisada. Incluye record_id, huella del registro, motivos, acciones de mejora y:

- Veracidad y trazabilidad: 0–40. Toda frase debe poder respaldarse con el perfil/evidencia; una afirmación falsa o sin soporte material bloquea el uso, aunque el total sea alto.
- Relevancia para responsabilidades y requisitos: 0–25. Prioriza experiencia concreta; no añadas palabras clave sin experiencia.
- Claridad y evidencia: 0–15. Acciones específicas, alcance y resultados verificables; evita repetición y frases vacías. No exijas números donde nunca se midieron.
- Idioma y consistencia: 0–10. Idioma de la oferta, fechas, nombres, terminología, ortografía y nivel lingüístico real.
- Integridad y presentación del PDF: 0–10. Texto seleccionable/legible, contacto, secciones, ausencia de cortes y páginas conforme al perfil. La CLI comprueba el contenido; inspecciona visualmente si es posible. Si no puedes hacerlo, indica `visual_check: not_performed`, no lo marques como aprobado visualmente.

Guarda `total`, `hard_blocks`, `improvements`, `visual_check` y `ready_to_apply` por separado. Un puntaje alto no anula problemas materiales, preguntas sin respuesta, restricciones geográficas o autorizaciones pendientes. La evaluación editorial del agente y la cobertura de la CLI son medidas distintas.

Antes de mejorar, escribe qué problema resolverá cada cambio. `revise` reutiliza el snapshot y produce otra versión/PDF sin llamada de IA. `generate` vuelve a usar IA y genera otra versión independiente; necesita registrar el motivo y conservar las anteriores. Compara con la versión previa para asegurarte de que una mejora no eliminó evidencia relevante.

## Respuestas y memoria

Aplica en orden estas reglas a cada campo.

1. Usa la respuesta verificada para la misma pregunta, alcance y período. Verifica la semántica después de traducir. Autorización de trabajo y necesidad de patrocinio son preguntas distintas. Diferencia disponibilidad para entrevista, fecha de inicio y preaviso. En inglés, conserva el nivel documentado y distingue comprensión de conversación.
2. Deriva respuestas que se desprenden inequívocamente del perfil. Para años de experiencia, suma intervalos profesionales documentados para el puesto o la tecnología consultada, sin contar dos veces meses simultáneos. Usa el requisito literal para distinguir trabajo profesional, estudio y proyectos personales. Si solo está verificada una parte, usa una opción que esa evidencia sustente y que represente con fidelidad la respuesta. Una ausencia en el CV por sí sola deja la respuesta sin verificar.
3. Redacta preguntas abiertas de interés, motivación o experiencia transferible con hechos de la oferta y del candidato. Usa una preferencia delegada, como expectativa negociable, dentro del alcance indicado. Cuando exista una opción veraz de «No aplica», «Desconocido» o «Prefiero no responder», selecciónala según el significado del campo.
4. Omite campos opcionales sin evidencia o autorización. Si queda un campo obligatorio sin respuesta veraz, un compromiso nuevo o una prueba que exija actuación personal, conserva el avance y sigue con otras vacantes. Agrupa al final los bloqueos que compartan la misma causa.

En el registro privado por oferta guarda pregunta, respuesta o impedimento, fuente, alcance y tipo (`verified`, `derived`, `delegated` o `unresolved`). Reutiliza hechos solo cuando el significado siga siendo equivalente. Retoma un caso pendiente al aparecer una respuesta, autorización o capacidad nueva, o si cambió el formulario.

No solicites automáticamente documentos de identidad, datos bancarios, contraseñas u otra información que la etapa no necesite. No almacenes claves, OTP o contraseñas en la campaña, la skill o el registro. Usa sesiones autorizadas o el gestor de credenciales disponible.

La automatización de búsqueda/formularios es dependiente de los portales: adapta el flujo leyendo el estado observable y respeta sus restricciones. Un selector roto no justifica continuar sin verificar la página ni sortear bloqueos.
