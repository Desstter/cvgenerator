# Selección, evaluación y mejora

## Evaluación de la oferta

Primero revisa condiciones excluyentes de la campaña: país desde el que se permite trabajar, ciudad presencial, modalidad, antigüedad máxima, disponibilidad, contrato y salario cuando está publicado. Un requisito desconocido se registra como desconocido y se resuelve antes de comprometer al candidato. Si no se publica salario, no se inventa una cifra ni se descarta automáticamente: aplica `unknown_salary_action`.

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

La nota es una rúbrica orientativa del agente y debe justificarse con la oferta y el perfil; no es una probabilidad de conseguir entrevista. Separa los requisitos por función: condiciones de elegibilidad (país, autorización, horario o contrato), capacidades centrales del trabajo y herramientas concretas. Marca un `hard_block` solo ante una condición de elegibilidad que falla o una competencia que la oferta declara expresamente imprescindible y que el candidato no demuestra. Una tecnología enumerada como ejemplo, preferida o aprendible no es por sí sola un bloqueo.

Evalúa el trabajo que la persona ya sabe hacer y su experiencia transferible antes de penalizar una herramienta desconocida. Por ejemplo, la falta de un lenguaje concreto no descarta automáticamente a quien domina otro lenguaje pertinente; la falta de un constructor visual no invalida experiencia real construyendo y manteniendo sitios WordPress; y la experiencia con herramientas de marketing relacionadas puede respaldar una candidatura sin afirmar que conoce todo el stack. Registra la brecha con precisión, pero no conviertas un requisito deseable o una herramienta sustituible en un rechazo automático. Solo presenta como dominio las herramientas verificadas; no inventes experiencia para mejorar el encaje.

Usa el umbral configurado para priorizar, explicando qué responsabilidades sí cubre la experiencia demostrada y qué requisitos específicos quedan por aprender o verificar. Puedes proponer candidaturas con brechas no excluyentes. No elimines una condición de elegibilidad verdaderamente excluyente por sumar puntos en otros aspectos.

## Salario y costos

Distingue salario publicado, expectativa del candidato y estimación de mercado. Si se solicita estimar salario, busca referencias recientes comparables por país, nivel, stack, horario y contrato; cita fuentes y expresa un rango con incertidumbre. Una moneda ambigua como `$` debe aclararse. Diferencia sueldo mensual/anual/por hora, bruto/neto y contrato laboral/contractor. No restes impuestos o aportes con cifras supuestas. Si se necesita conversión o normativa vigente, verifica una fuente actual.

Registra como costos del proceso el proveedor/modelo, si hubo refinamiento y el número de generaciones. No anuncies un costo exacto de API sin datos reales de uso y tarifas verificadas. Los portales que pidan pagar se detienen para decisión del usuario; no efectúes pagos por la autorización de postularse.

## Evaluación del CV

Crea `cv_assessment_<record_id>.json` después de `inspect` y actualízalo para la versión revisada. Incluye record_id, huella del registro, motivos, acciones de mejora y:

- Veracidad y trazabilidad: 0–40. Toda frase debe poder respaldarse con el perfil/evidencia; una afirmación falsa o sin soporte material bloquea el uso, aunque el total sea alto.
- Relevancia para responsabilidades y requisitos: 0–25. Prioriza experiencia concreta; no añadas palabras clave sin experiencia.
- Claridad y evidencia: 0–15. Acciones específicas, alcance y resultados verificables; evita repetición y frases vacías. No exijas números donde nunca se midieron.
- Idioma y consistencia: 0–10. Idioma de la oferta, fechas, nombres, terminología, ortografía y nivel lingüístico real.
- Integridad y presentación del PDF: 0–10. Texto seleccionable/legible, contacto, secciones, ausencia de cortes y páginas conforme al perfil. La CLI comprueba el contenido; inspecciona visualmente si es posible. Si no puedes hacerlo, indica `visual_check: not_performed`, no lo marques como aprobado visualmente.

Guarda `total`, `hard_blocks`, `improvements`, `visual_check` y `ready_to_apply` por separado. Un puntaje alto no anula problemas materiales, preguntas sin respuesta, restricciones geográficas o autorizaciones pendientes. La evaluación editorial del agente y la cobertura de la CLI son medidas distintas.

Antes de mejorar, escribe qué problema resolverá cada cambio. `revise` reutiliza el snapshot y produce otra versión/PDF sin llamada de IA. `generate` vuelve a usar IA y genera otra versión independiente; necesita registrar el motivo y conservar las anteriores. Compara con la versión previa para asegurarte de que una mejora no eliminó evidencia relevante.

## Respuestas y memoria

Cada respuesta reusable debe guardar pregunta, significado, respuesta, fuente, verificación y alcance. No uses la misma cifra para todas las tecnologías. Para referencias laborales, consentimiento de terceros, datos sensibles opcionales, pruebas técnicas, antecedentes o declaraciones legales, resuelve el caso concreto con el usuario y las reglas del entorno.

No solicites automáticamente documentos de identidad, datos bancarios, contraseñas u otra información que la etapa no necesite. No almacenes claves, OTP o contraseñas en la campaña, la skill o el registro. Usa sesiones autorizadas o el gestor de credenciales disponible.

La automatización de búsqueda/formularios es dependiente de los portales: adapta el flujo leyendo el estado observable y respeta sus restricciones. Un selector roto no justifica continuar sin verificar la página ni sortear bloqueos.
