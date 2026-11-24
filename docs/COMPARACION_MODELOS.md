# Comparación de modelos para hojas de vida

## Claves

En `.env`, reemplaza el valor de `OPENAI_API_KEY` por la nueva clave y pega la de DeepSeek en `DEEPSEEK_API_KEY`. Conserva `GOOGLE_API_KEY` para Gemini. Una sola clave por proveedor sirve para todos sus modelos disponibles en esa cuenta. No compartas `.env`, que está excluido de Git. La presencia de una clave no garantiza autenticación, saldo o acceso a un modelo.

El proveedor predeterminado es OpenAI con `gpt-6.2-sol` y tier estándar (`OPENAI_SERVICE_TIER` vacío); un `.env` existente puede sobrescribir estos valores. La comparación selecciona explícitamente el proveedor y modelo para cada ejecución; no hace falta cambiar `.env` entre modelos. Gemini no cambia de modelo automáticamente cuando se indica `--model`.

## Resultado de la prueba Luna Fast

Se ejecutaron 10 ofertas reales de LinkedIn × 5 instrucciones de estilo con un perfil sintético marcado «SIMULACION NO ENVIAR» (no es una postulación). Las 50 condiciones terminaron con PDF válido, 50/50 respetaron el idioma esperado, las 100 llamadas se sirvieron en `fast` y la mediana de generación fue 37.1 s. La revisión ciega por rúbrica dio 88.8/100 de media; las cinco instrucciones quedaron dentro del ruido (88.3–89.2), así que no hay evidencia para declarar una ganadora por calidad.

La prueba detectó una inconsistencia sistemática de voz en español (resumen en tercera persona con bullets en primera); se corrigió en los prompts y se validó con un piloto de 10 casos: 0/10 CV con voz mixta, 10/10 idioma y PDF correctos, 90.2/100 de nota ciega. El detalle reproducible está en [LUNA_FAST_2026-11-23.md](LUNA_FAST_2026-11-23.md).

## Comparación de 360 CVs y decisión final

Se ejecutaron 20 ofertas reales × 6 instrucciones de estilo × 3 modelos, con dos jueces ciegos y una rúbrica de 6 criterios. Sol quedó primero con ambos jueces: 82.4/100 con el juez Sol y 79.0/100 con el juez Luna, por delante de Luna (76.8/76.6) y Terra (76.7/76.2). Sol frente a Luna ganó 117 de 120 pares; Terra y Luna empataron. Sol costó unos USD 0.049 por CV (USD 4.85 por 100) y su mediana fue 33.6 s, frente a 38.6 s de Luna y 25.9 s de Terra.

**Decisión:** producción usa `gpt-6.2-sol` con tier estándar (`OPENAI_SERVICE_TIER` vacío, sin `fast`); el estilo `natural` quedó integrado en el prompt y se mantuvieron el guard de evidencia y la voz consistente. El benchmark se ejecutó con `fast` para comparar en igualdad de condiciones; retirarlo de producción es una decisión posterior. Luna queda como alternativa de bajo costo con `--model gpt-6-luna`. Detalle en [INFORME_V2_LUNA_TERRA_SOL.md](INFORME_V2_LUNA_TERRA_SOL.md).

## Modelos iniciales

El archivo `scripts/compare_models.py` enumera la matriz: OpenAI GPT-6 Luna, GPT-6.1 Terra y GPT-6.2 Sol; DeepSeek Flash y V4 Pro; Gemini 2.5 Flash y 3.8 Flash. La disponibilidad y el costo dependen de cada cuenta y pueden cambiar. Una llamada fallida se registra y no bloquea las demás.

## Ejecución

Usa el Python funcional del entorno, desde la carpeta del repositorio. El workspace debe pertenecer a un candidato verificado y estar ya inicializado. Guarda una descripción completa por archivo UTF-8 `.txt`, con su URL y snapshot por separado. Estos archivos y los resultados contienen información privada. El directorio de salida debe ser nuevo.

```powershell
.\.venv314\Scripts\python.exe -m app.cli --workspace C:\privado\candidato doctor
.\.venv314\Scripts\python.exe scripts\compare_models.py --workspace C:\privado\candidato --jobs C:\privado\ofertas --out C:\privado\comparacion-01
```

El script invoca la generación y `inspect` de forma secuencial para cada combinación, sin enviar solicitudes de empleo. Guarda tiempos, identificador de versión, hash de la oferta, resultado, errores y revisión para cada corrida. También guarda en `usage.jsonl` el consumo informado por el proveedor cuando esté disponible. Los PDF están en el workspace del generador y deben inspeccionarse antes de usarse. No aprueba afirmaciones ni exporta versiones sin revisión. El costo no se calcula automáticamente: hay que aplicar las tarifas vigentes y cotejar con la facturación real.

## Evaluación

Usa la misma oferta, perfil, plantilla y configuración para cada modelo. Revisa ciegamente los CV y registra afirmaciones no respaldadas, omisiones importantes, pertinencia, claridad y diseño con una rúbrica definida antes de puntuar. Un error factual grave impide dar por apto un CV, aunque obtenga una nota alta. Los porcentajes son puntuaciones de esa rúbrica, no probabilidades de selección ni predicciones de ATS. Compara tiempos, errores, número de correcciones y costo real cuando se disponga de él. No hagas postulaciones durante esta prueba.
