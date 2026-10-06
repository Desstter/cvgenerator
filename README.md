# CV Generator

Generador personal de CVs adaptados a una oferta. Usa un perfil editable o importa un PDF, revisa los datos extraídos y genera una versión con Claude, OpenAI o Gemini.

## Stack

Python · FastAPI · Jinja2 · PyMuPDF · xhtml2pdf · Anthropic API · OpenAI API · Google Generative AI

## Features

- **Perfiles independientes** — conserva por separado el CV de Developer y el CV de Bilingual Customer Service
- **Adaptación con revisión de hechos** — protege identidad, cargos, tecnologías, educación e idiomas; bloquea cifras y herramientas nuevas sin evidencia, y pide confirmar las frases reescritas
- **Catálogo de ofertas reales** — carga snapshots trazables de LinkedIn con enlace, fecha de verificación, estado y nota de ajuste
- **BPO honesto** — bloquea experiencia directa, métricas, CRM o niveles de inglés no verificados
- **CV bilingüe de una página** — plantilla inglesa compacta, sin GitHub ni bloques técnicos, validada antes de descargar
- **CV técnico de una página** — muestra experiencia, educación, idiomas, habilidades seleccionadas y proyectos o certificaciones si existen
- **Revisión antes de descargar** — muestra cada frase nueva junto a la evidencia fuente más cercana; permite editar y regenerar el PDF sin llamar de nuevo a la IA
- **PDF comprobado** — lee el archivo generado y verifica que estén presentes el contacto, el resumen y los bullets esperados
- **Versiones reproducibles** — el historial guarda la oferta, el CV fuente, la adaptación, el modelo, la plantilla, la cobertura y la revisión; cada edición crea una versión nueva y permite registrar si hubo entrevista u oferta
- **Multi-modelo** — elige entre Claude (Anthropic), GPT-4 (OpenAI) o Gemini (Google) para la generación
- **Análisis de PDF** — extrae el contenido de tu CV actual con PyMuPDF
- **Optimización por rol** — adapta el lenguaje, keywords y énfasis al puesto específico
- **Templates** — plantillas Jinja2 renderizadas con Chromium y fallback a xhtml2pdf
- **API REST** — endpoints FastAPI documentados con Swagger UI

## Flujo recomendado

1. Selecciona `Developer` o `Bilingual Customer Service` en **CV Profile**.
2. Elige una oferta real del catálogo, pega otra descripción o descarga el CV base.
3. Si importas un PDF, comprueba cargos, fechas, contacto y tecnologías antes de adaptarlo.
4. Revisa la cobertura estimada de términos y cada afirmación reescrita. Corrige el contenido y vuelve a generar el PDF si hace falta.
5. Confirma la revisión y descarga el PDF. El perfil BPO usa la plantilla inglesa de una página.

La cobertura de términos es una medida local: no predice el resultado de un sistema ATS externo. Una coincidencia solo cuenta cuando hay una frase concreta en el CV; las equivalencias propuestas por la IA no aumentan la puntuación. La revisión automática tampoco demuestra por sí sola que una paráfrasis sea cierta: el usuario confirma las afirmaciones nuevas antes de descargar.

En **Edit CV** puedes añadir hechos por empleo como `acción | alcance | resultado | métrica | fuente`. De los hechos estructurados se envían a la IA los marcados como verificados, junto al contexto real ya guardado. Cada guardado del perfil conserva la versión previa en `CV_DATA_DIR/revisions/`.

Para regenerar las cuatro muestras automatizadas sin alterar el historial de la app:

```bash
python scripts/generate_real_examples.py --provider gemini
```

Los PDF quedan en `output/pdf/` y el manifiesto de QA en
`output/real_offers_manifest.json`.
El manifiesto incluye la revisión pendiente de las frases reescritas; estas muestras requieren comprobación humana antes de usarse para una solicitud real.
Audita las muestras guardadas sin gastar llamadas de IA con `python scripts/evaluate_manifest.py`.

## CLI y postulaciones portables

`python -m app.cli --help` permite inicializar un candidato explícito en un workspace
privado, generar, inspeccionar, corregir, confirmar con evidencia y exportar un CV,
sin usar la interfaz ni iniciar un servidor. Cada workspace pertenece a una persona;
la CLI nunca usa el perfil personal empaquetado como identidad por defecto.

```powershell
.\.venv\Scripts\python.exe -m app.cli --workspace C:\Postulaciones\persona-a init --candidate C:\Postulaciones\candidate.json
.\.venv\Scripts\python.exe -m app.cli --workspace C:\Postulaciones\persona-a generate --job C:\Postulaciones\job.txt --provider gemini
```

La skill [`job-application-assistant`](skills/job-application-assistant/SKILL.md)
contiene el flujo para evaluar ofertas, revisar y mejorar el CV, completar formularios
y verificar el envío. Sus criterios y datos personales se configuran por separado.
`track` registra estados y comprobantes; no envía solicitudes por sí mismo. El agente
necesita herramientas de navegador y autorización para los destinos/datos de campaña.

`python scripts/package_application_assistant.py --out RUTA_DE_ENTREGA` crea un ZIP
portable con skill, muestras ficticias y generador CLI sin claves ni perfiles personales.
También produce el documento autocontenido
[`POSTULACIONES_PORTABLE.md`](docs/POSTULACIONES_PORTABLE.md), para copiarlo a otro chat.

El propietario autoriza el mantenimiento autónomo del generador, la CLI y la skill,
incluidos integración de versiones, commits y push cuando corresponda. El alcance
y las reglas para conservar/verificar el trabajo están en [`AGENTS.md`](AGENTS.md).

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
