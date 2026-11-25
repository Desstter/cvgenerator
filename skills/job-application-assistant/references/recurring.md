# Exploración programada de vacantes

Usa una automatización local del proyecto de empleo para buscar en segundo plano. Una ejecución programada de exploración produce una cola privada de vacantes verificadas y priorizadas. La corrida de postulación consume esa cola y sigue el flujo de la skill.

## Ejecución de exploración

1. Carga la campaña indicada por la automatización y comprueba que el perfil y el workspace correspondan a la misma persona. Si la campaña privada ya no existe o la identidad es ambigua, informa el impedimento y termina la ejecución.
2. Consulta en lectura el registro de postulaciones, las colas recientes y las búsquedas previas. Prioriza las ofertas nuevas, los portales oficiales y los ATS para los que exista una ruta accesible. Usa Brave cuando la herramienta esté disponible. Si el entorno programado carece de Brave, usa las herramientas de búsqueda pública disponibles para verificar la oferta en la fuente oficial. Conserva el límite de antigüedad de la campaña y deduplica por URL, ID de vacante o empresa/cargo/ubicación.
3. Evalúa las mejores coincidencias con la rúbrica de [workflow.md](workflow.md) y prepara un máximo de cinco finalistas por corrida cuando la automatización no fije otro límite. Guarda título, empresa, ubicación, modalidad, descripción, URL fuente y del portal, fechas observadas, puntuación, motivos, requisitos pendientes y el siguiente paso. Si el portal requiere sesión, registra ese hecho y continúa. Usa únicamente consultas públicas sin datos personales y mantén la evaluación del perfil en el workspace privado. Este modo termina al publicar la cola local.
4. Escribe `scout/<id-de-ejecucion>.json` dentro del workspace. Usa un ID único, registra hora con zona y guarda juntos `jobs`, `sources_checked` y `blockers`. Publica el archivo completo mediante un temporal renombrado en la misma carpeta. Mantén el registro de postulaciones, el CV y el historial en modo lectura durante esta corrida. Si falla una fuente, registra la limitación y prueba las demás fuentes disponibles.
5. Informa los finalistas nuevos o un impedimento que afecte la corrida. En la próxima postulación, revisa las colas más recientes, vuelve a comprobar la vigencia y deduplica contra el registro actual antes de crear un CV. La cola es una lista de vacantes por evaluar y confirmar en el flujo normal.

## Ampliación a preparación o envío

Antes de programar más etapas, comprueba en el entorno programado la CLI y el proveedor autorizado, la vista del formulario, el adjunto y, si aplica, la identidad de la sesión del portal. La preparación y el envío deben compartir la misma exclusión de escritura por workspace que las corridas manuales. La escritura atómica de cada archivo no serializa el flujo completo. Prueba con una corrida de preparación y verifica la reanudación antes de habilitar envíos programados.

Para habilitar envíos programados, usa una campaña que autorice expresamente esa ejecución recurrente, con destinos y límite por corrida. Si la herramienta o el portal requieren intervención puntual, conserva el caso, sigue con las ofertas accesibles y agrupa los pendientes. Cuando falte navegador, adjunto o sesión, explora y guarda la cola o conserva los CVs ya listos dentro del alcance autorizado. Los registros `submitting` y `uncertain` requieren reconciliación antes de cualquier nuevo intento.
