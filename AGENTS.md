# Mantenimiento autorizado de CV Generator

El propietario autorizó expresamente mejorar y cambiar este generador, su código,
su CLI y la skill `job-application-assistant` en cualquier momento mientras se
trabaja en el proyecto. Se permite corregir errores, refactorizar, ajustar modelos,
plantillas, pruebas e instrucciones, integrar versiones locales/remotas y hacer
commits y push al remoto configurado cuando convenga para entregar el resultado.
No se requiere pedir otra aprobación para cada mejora técnica dentro de ese alcance.

Antes de integrar versiones, inspecciona los cambios locales y remotos. Conserva
el trabajo existente con un respaldo recuperable y combina las mejoras compatibles;
no elijas una versión completa automáticamente por ser local o remota. Verifica
los cambios antes de publicar y usa push normal, sin reescribir historia compartida.

Esta autorización técnica no modifica los datos verdaderos del candidato ni concede
permiso para enviar postulaciones, aceptar compromisos laborales o publicar datos
personales. Esos pasos siguen el alcance de la campaña y la autorización del usuario.
No incluyas claves, historiales, documentos generados o archivos personales ajenos al
código en un commit o paquete portable.

El generador se controla por `python -m app.cli` en la automatización de postulaciones.
Cada persona usa un workspace explícito. Mantén revisión de afirmaciones, versiones,
validación del PDF, registro de estados y protección contra envíos duplicados.
Las interfaces API/CLI deben continuar usando el mismo flujo de generación y revisión.

La skill fuente está en `skills/job-application-assistant/`. Después de cambiarla,
actualiza su copia instalada cuando exista y regenera el manual y ZIP con
`python scripts/package_application_assistant.py --out RUTA_DE_ENTREGA`.
Valida la skill y ejecuta las pruebas apropiadas; el flujo completo se verifica con
`python -m pytest -q`. Las pruebas de generación utilizan IA simulada y PDFs reales,
sin llamadas pagadas ni postulaciones externas.
