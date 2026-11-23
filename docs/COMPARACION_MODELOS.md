# Comparación de modelos para hojas de vida

## Claves

En `.env`, reemplaza el valor de `OPENAI_API_KEY` por la nueva clave y pega la de DeepSeek en `DEEPSEEK_API_KEY`. Conserva `GOOGLE_API_KEY` para Gemini. Una sola clave por proveedor sirve para todos sus modelos disponibles en esa cuenta. No compartas `.env`, que está excluido de Git. La presencia de una clave no garantiza autenticación, saldo o acceso a un modelo.

El proveedor predeterminado es OpenAI con `gpt-6-luna` y `OPENAI_SERVICE_TIER=fast`; un `.env` existente puede sobrescribir estos valores. La comparación selecciona explícitamente el proveedor y modelo para cada ejecución; no hace falta cambiar `.env` entre modelos. Gemini no cambia de modelo automáticamente cuando se indica `--model`.

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
