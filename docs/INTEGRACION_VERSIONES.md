# Integración de las versiones local y remota

Se comparó el trabajo local pendiente con `origin/main` en `50823e1`, después de
incorporar los commits remotos `3fd2d92` y `50823e1`. El trabajo local anterior al
pull se conserva además en el stash `codex-preserve-local-before-pull-2026-10-05`.
La versión final combina las mejoras compatibles de ambos lados.

| Área | Decisión y motivo |
|---|---|
| Dependencias y Gemini | Conservar las versiones y el cliente `google-genai` del remoto, incluidos timeout y desactivación de telemetría; mantener del local el registro del modelo realmente usado. |
| Adaptación y prompts | Conservar la selección de habilidades verificadas, la protección de cargos/fechas y las restricciones sobre cifras. El refinamiento recibe el CV fuente y contexto, además de la adaptación inicial. |
| Cobertura de términos | Conservar la medida local con evidencia concreta y límites de palabra. El flujo de generación no usa equivalencias inventadas por la IA para subir el puntaje. |
| Historial y revisión | Conservar snapshots reproducibles, revisión de afirmaciones, edición sin otra llamada de IA, versiones enlazadas y resultados de la candidatura. |
| PDF | Conservar `pymupdf` del remoto y la validación de contenido del local. Usar plantillas en vez de reemplazar fragmentos directamente en un PDF, que podía truncar texto. Ampliar la validación a habilidades, educación, idiomas y contacto; escapar el contenido HTML. |
| Interfaz | Conservar la revisión del CV importado y de frases reescritas, las ediciones con regeneración y el historial con seguimiento. La automatización usa CLI. |
| CLI y portabilidad | Conservar workspaces por persona, revisión con evidencia, validación del archivo exportado y registro que bloquea duplicados y reintentos inciertos. El ZIP incluye el runtime sin perfiles ni claves personales. |
| Perfil corrupto y peticiones inválidas | Fallar con un error claro en vez de sustituir silenciosamente una identidad por el perfil empaquetado. Rechazar ofertas vacías y plantillas inválidas antes de usar IA. |
| Permisos de mantenimiento | Documentar la autorización expresa del propietario en `AGENTS.md`, skill, manual y campaña local: se pueden mejorar código e instrucciones, integrar versiones y publicar commits en el remoto configurado. |

La autorización de mantenimiento es distinta del alcance de una campaña de
postulaciones. Los datos, documentos generados e historiales permanecen locales.
Los archivos de imágenes y resultados no verificados que ya existían no forman
parte de esta integración de código.

La validación ejecuta la suite de pytest, el flujo CLI con proveedor simulado y
PDFs reales, la ejecución del paquete extraído sin datos personales, la sintaxis
de JavaScript y Python, el validador de la skill y `git diff --check`.
