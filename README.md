# CV Generator

Generador de CVs/resumes potenciado por IA. Sube tu CV actual (PDF) y una descripción del puesto al que aplicas, y la app genera una versión optimizada usando **Claude, GPT-4 o Gemini** según prefieras.

## Stack

Python · FastAPI · Jinja2 · PyMuPDF · xhtml2pdf · Anthropic API · OpenAI API · Google Generative AI

## Features

- **Perfiles independientes** — conserva por separado el CV de Developer y el CV de Bilingual Customer Service
- **Adaptación verificable** — en ambos perfiles protege identidad, cargos, tecnologías, educación, idiomas y el inventario real de habilidades
- **Catálogo de ofertas reales** — carga snapshots trazables de LinkedIn con enlace, fecha de verificación, estado y nota de ajuste
- **BPO honesto** — bloquea experiencia directa, métricas, CRM o niveles de inglés no verificados
- **CV bilingüe de una página** — plantilla inglesa compacta, sin GitHub ni bloques técnicos, validada antes de descargar
- **CV técnico de una página** — orden ATS de resumen, competencias, experiencia, educación e idiomas
- **Revisión antes de descargar** — muestra el contenido generado y una auditoría de afirmaciones
- **Multi-modelo** — elige entre Claude (Anthropic), GPT-4 (OpenAI) o Gemini (Google) para la generación
- **Análisis de PDF** — extrae el contenido de tu CV actual con PyMuPDF
- **Optimización por rol** — adapta el lenguaje, keywords y énfasis al puesto específico
- **Templates** — plantillas Jinja2 renderizadas con Chromium y fallback a xhtml2pdf
- **API REST** — endpoints FastAPI documentados con Swagger UI

## Flujo recomendado

1. Selecciona `Developer` o `Bilingual Customer Service` en **CV Profile**.
2. Elige una oferta real del catálogo, pega otra descripción o descarga el CV base.
3. Revisa el análisis ATS, la auditoría de afirmaciones y el contenido completo.
4. Descarga el PDF generado. El perfil BPO siempre usa la plantilla inglesa de una página.

Para regenerar las cuatro muestras auditadas sin alterar el historial de la app:

```bash
python scripts/generate_real_examples.py --provider gemini
```

Los PDF finales quedan en `output/pdf/` y el manifiesto de QA en
`output/real_offers_manifest.json`.

## Setup

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Agregar tus API keys: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY

# Iniciar servidor
uvicorn app.main:app --reload
```

Abre `http://localhost:8000/docs` para la documentación interactiva de la API.

### Despliegue

Configura las claves de IA en `.env`. Para no perder ediciones ni PDFs al actualizar el
código, define `CV_DATA_DIR`, `UPLOADS_DIR`, `OUTPUTS_DIR` y `SAVED_DIR` en rutas
persistentes fuera del checkout (ver `.env.example`). El historial se guarda en
`CV_DATA_DIR/history.json` y no se versiona en Git. Antes de migrar una instalación
existente, copia allí sus perfiles e historial.

Si se publica detrás de un proxy con autenticación, inicia Uvicorn en
`127.0.0.1` para que el puerto de la aplicación no quede expuesto directamente.

## Estructura

```
app/
├── main.py           # FastAPI app y endpoints
├── config.py         # Configuración y variables de entorno
├── models/           # Schemas Pydantic
├── services/         # Lógica de generación con cada modelo de IA
├── prompts/          # System prompts para los modelos
├── templates/        # Templates Jinja2 para el CV
├── data/              # CVs base y catálogo trazable de ofertas
└── static/           # Assets estáticos
scripts/               # Generación reproducible de muestras reales
```
