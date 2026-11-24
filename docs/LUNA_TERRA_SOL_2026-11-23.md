# Luna vs Terra vs Sol: 10 ofertas x 5 prompts

Simulación de 10 ofertas reales de LinkedIn × 5 instrucciones de estilo × 3 modelos de OpenAI,
con el mismo perfil sintético marcado «SIMULACION NO ENVIAR», la misma plantilla y el mismo flujo de dos pasadas.
Ningún CV es una postulación ni representa a una persona real.

## Diseño y evaluación

- 150 condiciones; terminadas e inspeccionables: 150.
- Todos los modelos usan service_tier=fast, la misma plantilla técnica y los mismos prompts (incluida la corrección de voz).
- La nota ciega se calcula por oferta: los CV completados de los tres modelos y los cinco estilos se mezclan y se evalúan sin etiqueta de modelo, con rúbrica de 4 × 25 puntos.
- La rúbrica mide consistencia de idioma, especificidad, pertinencia y naturalidad; no mide veracidad factual ni predice contratación.

## Resultado global por modelo

| Modelo | PDF / casos | Idioma | Mediana | USD / CV | Nota ciega | Voz mixta |
|---|---|---|---|---|---|---|
| gpt-6-luna | 50 / 50 | 50 / 50 | 35.6 s | USD 0.00348 | 85.9 | 0 / 35 |
| gpt-6.1-terra | 50 / 50 | 50 / 50 | 24.3 s | USD 0.02429 | 84.2 | 1 / 35 |
| gpt-6.2-sol | 50 / 50 | 50 / 50 | 32.6 s | USD 0.04826 | 86.7 | 0 / 35 |

## Comparación emparejada (misma oferta y prompt)

| Diferencia | Media | Mediana | Gana / Empata / Pierde | Mín / Máx |
|---|---|---|---|---|
| Terra - Luna | -1.68 | -1.0 | 6 / 10 / 34 | -8 / +6 |
| Sol - Luna | +0.82 | +1.0 | 28 / 7 / 15 | -7 / +6 |
| Sol - Terra | +2.50 | +2.0 | 37 / 7 / 6 | -3 / +12 |

## Desglose de la nota ciega

| Modelo | Lenguaje /25 | Especificidad /25 | Pertinencia /25 | Naturalidad /25 | Total /100 |
|---|---|---|---|---|---|
| gpt-6-luna | 23.2 | 22.0 | 18.7 | 22.0 | 85.9 |
| gpt-6.1-terra | 23.1 | 21.2 | 18.2 | 21.8 | 84.2 |
| gpt-6.2-sol | 23.3 | 21.9 | 18.9 | 22.6 | 86.7 |

## Nota ciega por modelo × instrucción

| Modelo | impacto | reclutador | natural | enfoque | breve |
|---|---|---|---|---|---|
| gpt-6-luna | 86.2 | 85.6 | 85.9 | 86.6 | 85.3 |
| gpt-6.1-terra | 84.3 | 84.9 | 83.1 | 85.1 | 83.8 |
| gpt-6.2-sol | 86 | 86.6 | 87.1 | 87.2 | 86.8 |

## Mediana de tiempo por modelo × instrucción

| Modelo | impacto | reclutador | natural | enfoque | breve |
|---|---|---|---|---|---|
| gpt-6-luna | 34.8 s | 33.1 s | 39.0 s | 37.0 s | 34.3 s |
| gpt-6.1-terra | 24.5 s | 24.3 s | 24.1 s | 26.6 s | 24.2 s |
| gpt-6.2-sol | 34.0 s | 31.1 s | 33.6 s | 31.8 s | 30.7 s |

## Nota ciega por modelo × oferta

| Oferta | Luna | Terra | Sol |
|---|---|---|---|
| [avancop](https://co.linkedin.com/jobs/view/desarrollador-mobile-flutter-at-avancop-cooperativa-de-ahorro-y-cr%C3%A9dito-4386956002) | 81.2 | 82.2 | 80.8 |
| [Desarrollador(a) Mobile en Bision Consulting — Bogot…](https://co.linkedin.com/jobs/view/desarrollador-a-mobile-at-bision-consulting-4489103733) | 84.6 | 83 | 84.2 |
| [cambio](https://co.linkedin.com/jobs/view/desarrollador-a-backend-python-django-cambio-colombia-at-cambio-colombia-4252592127) | 90.8 | 87 | 93.4 |
| [cheil](https://co.linkedin.com/jobs/view/full-stack-developer-ingl%C3%A9s-at-cheil-colombia-4482758085) | 90.4 | 90 | 92 |
| [infinita](https://co.linkedin.com/jobs/view/backend-python-developer-at-infinita-consulting-4470023726) | 86.2 | 81.2 | 83.8 |
| Desarrollador Backend Junior - Bogotá | 90.8 | 89.6 | 94.4 |
| [ncloudx](https://co.linkedin.com/jobs/view/mid-level-full-stack-developer-ai-native-at-ncloudx-4489196084) | 89 | 88 | 90.4 |
| [ntt](https://co.linkedin.com/jobs/view/desarrollador-a-mobile-flutter-junior-at-ntt-data-europe-latam-4466587919) | 86.6 | 86 | 86.4 |
| Full Stack Engineer \| React.js, TypeScript & AWS Lambda | 86.6 | 83.6 | 86 |
| [Desarrollador(a)  de APIs e Integraciones  en Organi…](https://co.linkedin.com/jobs/view/desarrollador-a-de-apis-e-integraciones-at-terpel-4489648273) | 73 | 71.8 | 76 |

## Revisión de afirmaciones y calidad editorial

| Modelo | No respaldadas | A revisar | Problemas editoriales | Dos pasadas |
|---|---|---|---|---|
| gpt-6-luna | 0 | 603 | 0 | 50 |
| gpt-6.1-terra | 0 | 620 | 0 | 50 |
| gpt-6.2-sol | 0 | 644 | 0 | 50 |

## Lectura

- La comparación de nota es válida dentro de esta muestra: mismo perfil, mismas ofertas, mismos prompts y evaluación ciega por oferta.
- Las diferencias de tiempo incluyen concurrencia, cuota y orden de ejecución; no son un benchmark aislado de latencia.
- El costo es nominal, sin descuentos de caché, y se calcula con los tokens comunicados por el proveedor.
- Una nota alta no demuestra que cada afirmación sea verdadera: los CV siguen siendo borradores de simulación pendientes de revisión.

## Veredicto

- **Calidad de CV dentro de esta muestra:** Sol 86.7 > Luna 85.9 > Terra 84.2. La ventaja de Sol sobre Luna es pequeña (+0.82 de media; gana 28, empata 7 y pierde 15 de 50 pares) y no es concluyente. La ventaja de Sol sobre Terra sí es consistente (+2.50; gana 37, empata 7 y pierde 6).
- **Velocidad:** Terra 24.3 s < Sol 32.6 s < Luna 35.6 s. Terra produce además CV unas 7% más cortos (1.758 vs 1.894 caracteres), así que parte de su ventaja es que escribe menos.
- **Costo nominal:** Luna USD 0.00348 < Terra USD 0.02429 < Sol USD 0.04826 por CV; por 100 CV, aproximadamente USD 0.35 / 2.43 / 4.83.
- **Producción:** se mantiene **Luna Fast**. Ocho décimas de punto no justifican 14× el costo, y Luna empata en fiabilidad, idioma, fidelidad y voz.
- **Alternativa premium:** **Sol** es defendible si se quiere exprimir el último punto de calidad y el costo es irrelevante (unos 5 centavos por CV).
- **Terra:** no. Es el más rápido, pero el de menor nota y cuesta 7× Luna; no compensa.

El juez es gpt-6-luna y evalúa 50 casos por modelo; la comparación es válida dentro de esta muestra, no una clasificación definitiva.
