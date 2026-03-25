# CV Generator

Generador de CVs/resumes potenciado por IA. Sube tu CV actual (PDF) y una descripción del puesto al que aplicas, y la app genera una versión optimizada usando **Claude, GPT-4 o Gemini** según prefieras.

## Stack

Python · FastAPI · Jinja2 · PyMuPDF · xhtml2pdf · Anthropic API · OpenAI API · Google Generative AI

## Features

- **Multi-modelo** — elige entre Claude (Anthropic), GPT-4 (OpenAI) o Gemini (Google) para la generación
- **Análisis de PDF** — extrae el contenido de tu CV actual con PyMuPDF
- **Optimización por rol** — adapta el lenguaje, keywords y énfasis al puesto específico
- **Templates** — plantillas Jinja2 con renderizado a PDF via xhtml2pdf
- **API REST** — endpoints FastAPI documentados con Swagger UI

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

## Estructura

```
app/
├── main.py           # FastAPI app y endpoints
├── config.py         # Configuración y variables de entorno
├── models/           # Schemas Pydantic
├── services/         # Lógica de generación con cada modelo de IA
├── prompts/          # System prompts para los modelos
├── templates/        # Templates Jinja2 para el CV
└── static/           # Assets estáticos
```
