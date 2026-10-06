# CLI local de cvgenerator

## Preparación

Requiere Python 3.12 o superior y las dependencias de `requirements.txt`. En Windows, desde el repositorio:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.cli --help
```

Usa el entorno existente si ya está configurado. No instales dependencias en el Python global para una campaña. En otros sistemas usa el intérprete del entorno equivalente (`.venv/bin/python`).

Las credenciales y modelos se obtienen de las variables de entorno/`.env` del generador. `doctor` muestra solo si hay claves configuradas, nunca sus valores. El proceso invoca los servicios Python locales de la aplicación; no necesita Uvicorn ni HTTP. `generate` envía CV y oferta al proveedor de IA seleccionado: ese proveedor debe estar autorizado para esos datos.

Cada llamada debe ser un proceso nuevo, en el repositorio y con el mismo workspace del candidato. La CLI fija `CV_DATA_DIR`, `OUTPUTS_DIR`, `SAVED_DIR` y `UPLOADS_DIR` antes de importar los servicios. No afecta los perfiles ni el historial usados por la interfaz gráfica. No usa un servidor remoto desplegado; para trabajar con datos de allí se necesita una exportación autorizada.

## Comandos

Todos aceptan argumentos globales **antes** del subcomando:

```text
python -m app.cli --workspace RUTA --profile developer --json-out RESULTADO.json SUBCOMANDO ...
```

`--profile` es `developer` por defecto; también admite `bilingual_customer_service`. Las personas se separan por workspace, no por estos dos tipos de CV. `--json-out` es opcional: stdout contiene el mismo JSON; logs/errores van a stderr. Un error termina con código 1. `--help` y errores de argumentos usan el comportamiento de argparse.

| Subcomando | Argumentos | Resultado |
|---|---|---|
| `doctor` | ninguno | Rutas aisladas, proveedor y disponibilidad de claves |
| `init` | `--candidate candidate.json` | Importa BaseCVStore explícito; no sobrescribe una identidad existente |
| `profile` | ninguno | Exporta el perfil verificado del workspace |
| `profile-update` | `--candidate candidate.json` | Actualiza hechos conservando contacto/perfil; guarda revisión previa |
| `generate` | `--job job.txt [--provider claude\|openai\|gemini] [--template technical\|modern\|classic\|bilingual]` | Ejecuta adaptación/refinamiento, veracidad, cobertura, PDF e historial |
| `history` | ninguno | Versiones de CV y estado de revisión |
| `inspect` | `--record ID` | CV fuente/adaptado, evidencia, revisión, cobertura y validación del PDF |
| `revise` | `--record ID --cv edited_cv.json` | Revisa y renderiza CVData editado; devuelve un ID nuevo y mantiene parent_id |
| `confirm` | `--record ID --review review.json` | Guarda revisión individual con evidencia y huella de la versión |
| `export` | `--record ID --out final.pdf` | Copia PDF validado/revisado y devuelve SHA-256; no sobrescribe otro archivo |
| `applications` | ninguno | Lee el registro de postulaciones para continuar |
| `track` | `--job job.json --state ESTADO [--record ID] [--note TEXTO] [--evidence receipt.json]` | Registra un estado observado; no opera el navegador ni envía nada |

`candidate.json` es un `BaseCVStore`; `edited_cv.json` es solamente el objeto `CVData`, sin envoltorio `cv`. El idioma del CV se determina por la oferta en el generador. La plantilla BPO mantiene sus restricciones de una página. No cambies código para silenciar el guardián de afirmaciones.

## Ejemplo completo

Los siguientes valores son rutas de ejemplo. Sustitúyelos por la configuración de campaña; en PowerShell:

```powershell
$cvPython = '.\.venv\Scripts\python.exe'
$cvWorkspace = 'C:\Postulaciones\persona-a'
& $cvPython -m app.cli --workspace $cvWorkspace doctor
& $cvPython -m app.cli --workspace $cvWorkspace init --candidate 'C:\Postulaciones\candidate.json'
& $cvPython -m app.cli --workspace $cvWorkspace --json-out 'C:\Postulaciones\generated.json' generate --job 'C:\Postulaciones\job.txt' --provider gemini
```

Lee `record_id` del resultado, no uses una posición del historial. Para inspeccionar:

```powershell
$cvRecord = 'ID_DEVUELTO'
& $cvPython -m app.cli --workspace $cvWorkspace --json-out 'C:\Postulaciones\inspection.json' inspect --record $cvRecord
```

Extrae `adapted_cv` a `edited_cv.json` si hay que corregirlo, y el `review_template` a `review.json` si hay afirmaciones pendientes. Cada decisión debe ser `supported`, incluir `reason` y una `evidence_quote` literal del CV fuente/contexto verificado. Conserva `record_id` y `record_fingerprint`. La CLI verifica la cita y la versión; el revisor debe comprobar que la evidencia realmente respalde la frase completa. Las decisiones `unresolved` o rechazadas deben resolverse con corrección o nuevos hechos verificados, no aprobación ficticia.

```powershell
& $cvPython -m app.cli --workspace $cvWorkspace revise --record $cvRecord --cv 'C:\Postulaciones\edited_cv.json'
# Si revise devuelve otro record_id, úsalo y vuelve a ejecutar inspect.
& $cvPython -m app.cli --workspace $cvWorkspace confirm --record $cvRecord --review 'C:\Postulaciones\review.json'
& $cvPython -m app.cli --workspace $cvWorkspace export --record $cvRecord --out 'C:\Postulaciones\CV_Empresa_Cargo.pdf'
```

No hace falta `confirm` cuando el generador ya ha marcado la versión como revisada (`reviewed: true`); sí hace falta la revisión completa del agente para decidir que está lista. Si cambiaste el contacto a otra identidad o necesitas corregir contacto, crea un workspace nuevo explícito; `profile-update` no cambia el contacto.

## Registro de postulaciones

Secuencia habitual: `discovered -> shortlisted -> cv_ready -> prepared -> submitting -> submitted`.

Estados alternativos: `awaiting_user`, `skipped`, `failed` y `uncertain`. La CLI valida transiciones: no se puede declarar `submitted` directamente desde `discovered`. `cv_ready`, `prepared`, `submitting` y `submitted` requieren una versión revisada cuyo PDF siga siendo válido y cuya descripción coincida con el snapshot de la oferta.

```powershell
& $cvPython -m app.cli --workspace $cvWorkspace track --job 'C:\Postulaciones\job.json' --state discovered
& $cvPython -m app.cli --workspace $cvWorkspace track --job 'C:\Postulaciones\job.json' --state shortlisted --note 'Evaluación guardada en job_assessment.json'
& $cvPython -m app.cli --workspace $cvWorkspace track --job 'C:\Postulaciones\job.json' --state cv_ready --record $cvRecord
& $cvPython -m app.cli --workspace $cvWorkspace track --job 'C:\Postulaciones\job.json' --state prepared --record $cvRecord
& $cvPython -m app.cli --workspace $cvWorkspace track --job 'C:\Postulaciones\job.json' --state submitting --record $cvRecord
# El agente realiza el envío autorizado en el navegador y observa el resultado.
& $cvPython -m app.cli --workspace $cvWorkspace track --job 'C:\Postulaciones\job.json' --state submitted --record $cvRecord --evidence 'C:\Postulaciones\receipt.json'
```

`receipt.json` necesita `confirmation_text`, `observed_at` (ISO 8601 con zona horaria) y `destination_url` HTTPS. El agente debe haber observado esa evidencia: la CLI no comprueba por Internet su autenticidad. Un registro no sustituye una confirmación del portal.

Ante incertidumbre, marca `uncertain`; el registro impide preparar/enviar de nuevo. Si observas que no se recibió, usa `failed` con evidencia que incluya `not_submitted_verified: true` y `confirmation_text` explicando la comprobación, y luego retoma. Una postulación `submitted` bloquea un segundo envío con la misma URL normalizada y perfil. Para URLs diferentes de la misma oferta, compara manualmente antes de generar.

## Archivos para continuar

Dentro del workspace quedan `data/` (perfil, revisiones e historial), `saved/` (PDFs persistentes), `reviews/` (decisiones), `applications.json` (estados y eventos) y las salidas de trabajo. Guarda también snapshots, evaluaciones y respuestas en carpetas por oferta. Es información personal: no la incluyas al distribuir la skill.

No ejecute dos campañas concurrentes en el mismo workspace: la escritura es atómica para evitar archivos truncados, pero el registro no tiene bloqueo entre procesos. Para distribuir el generador, copia el código sin `.env`, `.venv`, perfiles personales ni archivos generados.
