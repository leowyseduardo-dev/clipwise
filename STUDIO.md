# Clipwise Studio 1.3.0

## Primer proyecto

En Windows, abre **Abrir Clipwise.cmd** en la carpeta del proyecto o instala **Clipwise-Setup-1.3.0.exe**. Carga un archivo de video o pega enlaces compatibles. Al terminar el análisis, abre un clip para ver la frase de entrada, su puntuación, el desglose y las propuestas de edición.

En **Clip Battle**, genera una variante, reproduce las dos exportaciones y marca tu favorita. En el editor puedes cambiar el encuadre, la proporción, los subtítulos, la marca, el sonido y la entrada del clip. Aprueba la propuesta semanal para añadir las piezas al calendario. Las publicaciones en redes requieren una acción aparte.

## Cambios sobre la aplicación existente

| Área | Comportamiento en esta versión |
| --- | --- |
| Entrada | Se mantienen la carga de video, los enlaces compatibles y el historial. La carga por lotes crea proyectos independientes y conserva los elementos pendientes si falla un envío. |
| Selección | Combina palabras y límites de frases, audio y señales visuales disponibles. Extiende una pregunta cuando hay una respuesta cercana, reduce duplicados y registra qué análisis se ejecutaron. |
| Voces y rostros | Whisper aporta los tiempos de las frases. TitaNet-S compara muestras de voz localmente y asigna etiquetas anónimas. El movimiento de los labios orienta el encuadre cuando se detectan caras. Voces superpuestas, cambios rápidos de plano o fragmentos cortos reducen la precisión. |
| Evaluación | La puntuación de 0 a 100 ordena candidatos y se acompaña de factores y consejos. Su capacidad de predecir reproducciones queda pendiente de validación con publicaciones reales. |
| Hooks y estrategia | Ofrece frases que aparecen en el clip, variantes de entrada y recomendaciones para editar. Si hay un proveedor de lenguaje configurado, se comprueban sus propuestas contra la transcripción. Los recursos de apoyo sugeridos proceden del propio video. |
| Edición y marca | Renderiza MP4 en 1080 × 1920, 1080 × 1080 y 1920 × 1080. Mantiene exportación SRT, miniaturas y ZIP. Admite preferencias de tipografía, color, márgenes, marca de texto y logotipo PNG. |
| Clip Battle | Cada variante tiene su propio archivo de video y se puede reproducir. Una solicitud repetida para la misma variante recupera la existente. El favorito orienta las sugerencias de ese creador. |
| Calendario | Propone hasta siete piezas a partir de los clips disponibles, con día, plataforma y texto. Se puede aprobar el plan, consultar el calendario y quitar piezas. |
| Gestión de proyectos | Permite renombrar, archivar, restaurar y duplicar. Una copia conserva cortes, textos, subtítulos, variantes y medios con IDs nuevos. Las publicaciones, métricas, cargos y citas de calendario pertenecen al proyecto original. |
| Consumo | Muestra tokens comunicados por el proveedor, caché, tiempo de procesamiento y render, y almacenamiento. La transcripción se puede reutilizar cuando coinciden audio y ajustes. |
| Modo alojado | Registro e inicio de sesión, espacios por equipo, roles, créditos y suscripciones configurables con Stripe. El escritorio sigue disponible sin cuentas. |

## Ejecutar el modo alojado

Prepara Python 3.11, FFmpeg y FFprobe, Node.js y el modelo de Whisper. Desde la raíz, compila la interfaz con `npm ci --prefix web` y `npm run build --prefix web`. Instala las dependencias con `python -m pip install -r engine/requirements-hosted.txt`. Dentro de `engine`, inicia `python -m uvicorn cloud.main:app --host 127.0.0.1 --port 8000 --workers 1`. En Windows, la compilación de escritorio busca los ejecutables FFmpeg bajo `tools/ffmpeg`. Puedes recuperar TitaNet-S con `python tools/instalar_voces.py`.

| Configuración | Valor que debe aportar el operador |
| --- | --- |
| Clipwise_PUBLIC_ORIGIN | Origen público HTTPS del editor. Para pruebas locales se admite http en loopback. |
| Clipwise_CLOUD_DIR | Directorio persistente para cuentas, equipos y videos. Planifica copias de seguridad y espacio para los medios. |
| FFMPEG_BIN, FFPROBE_BIN, WHISPER_MODEL | Rutas de los binarios y del modelo. |
| STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET | Clave del servidor y secreto de firma del endpoint. Registra el webhook del dominio en `/api/account/webhook` para los eventos de suscripción. |
| STRIPE_PRICE_CREATOR, STRIPE_PRICE_PRO, STRIPE_PRICE_AGENCY | Identificadores de los tres precios recurrentes que defina el titular de la cuenta. |
| YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET | Credenciales de las aplicaciones aprobadas por cada proveedor. Registra la URI de retorno mostrada por Clipwise. YouTube y TikTok requieren autorización del usuario. |
| Clipwise_MODEL_RATES | Objeto JSON por modelo con su precio de entrada y salida en USD por millón de tokens, en ese orden. |
| Clipwise_RENDER_USD_HOUR, Clipwise_STORAGE_USD_GB_MONTH | Tarifas reales de cómputo y almacenamiento para estimar costes. |

El servidor alojado utiliza un motor privado por equipo activo. Usa un solo proceso de la puerta de acceso y un proxy HTTPS delante de él. `Clipwise_MAX_WORKSPACES` controla el máximo de motores activos. Los roles son propietario, editor y lector. El propietario puede añadir a su equipo a una persona que ya tenga cuenta. La configuración inicial de planes se encuentra en `engine/cloud/accounts.py`.

| Plan | Créditos al mes | Miembros | Trabajos activos |
| --- | ---: | ---: | ---: |
| Free | 3 | 1 | 1 |
| Creator | 30 | 1 | 4 |
| Pro | 120 | 3 | 10 |
| Agency | 500 | 10 | 30 |

Una operación de generación facturable consume un crédito. Estos créditos son una cuota interna de la aplicación. Los precios monetarios proceden de los productos configurados en Stripe. Las estadísticas de YouTube solo se importan al solicitarlo para videos publicados desde el proyecto y pertenecientes al canal conectado. Instagram y Facebook disponen de exportación y calendario.

## Verificación y alcance

Las pruebas de regresión cubren el motor, el escritorio, cuentas, roles, cuotas concurrentes y webhooks con pagos simulados. En Windows se verificó un flujo con video hablado, Whisper, subtítulos, audio, tres resoluciones, dos variantes y aprobación del calendario. También se comprobó la interfaz en Chrome de escritorio y con un ancho móvil de 390 píxeles.

Para repetir las pruebas desde `engine`, ejecuta `python -m pytest -q tests ../desktop/tests`. El caso audiovisual es `python tools/e2e/studio_workflow.py` desde la raíz. La versión alojada se probó localmente. El lanzamiento público requiere infraestructura, dominio, HTTPS y servicios de terceros del titular. Están pendientes la prueba de carga en ese servidor, una transacción real, una publicación autorizada en un canal real y la evaluación de retención con una muestra de audiencia. La comparación de voces es aproximada y puede dividir una misma voz en dos etiquetas.

## Registro por fase

| Fase | Base revisada | Cambio y comprobación |
| --- | --- | --- |
| 1. Auditoría | Aplicación de Windows con FastAPI, SQLite, React, Whisper, FFmpeg y una cola de trabajos. | Se ejecutaron 296 pruebas antes de introducir las funciones de Studio. Se conservaron el motor, la interfaz de proyectos y el formato de los datos existentes. |
| 2. Momentos | Selección de candidatos, transcripción y límites temporales. | Se probaron el solapamiento de ventanas, las frases completas, la recuperación de caché y las cuatro fuentes de análisis en una muestra hablada. |
| 3. Editor | Render normal, reencuadre, subtítulos y exportación. | Se comprobaron variantes con archivos distintos, selección de favorita, audio presente y dimensiones reales de los MP4. Dos solicitudes simultáneas de edición compiten por un único render. |
| 4. Personalización | Puntuación, transcripciones, temas y metadatos de publicación. | Las recomendaciones ordenan citas del video según los temas elegidos. Las métricas y el borrado de preferencias se probaron con identidades separadas. |
| 5. Equipos y calendario | Proyectos, fuentes locales y conexiones de publicación. | Se probó la separación entre dos equipos con motores independientes, admisión de trabajos concurrentes, permisos, plan semanal y copia de proyectos editados. |
| 6. Producto | Interfaz web, ejecutable y costes registrados. | La suite final de escritorio y servidor pasó 309 pruebas. Una dependencia emitió un aviso de futura obsolescencia. La compilación web y la comprobación de TypeScript terminaron correctamente. |

La prueba audiovisual de 18 segundos produjo 48 entradas de subtítulos con voz en inglés, seis propuestas de apertura y formatos vertical, cuadrado y horizontal. El modelo de voces también se probó con audio de cuatro interlocutores y produjo cinco etiquetas. Ese resultado muestra el margen de error de la identificación anónima. La validación de precisión editorial con videos largos, distintos acentos y resultados de audiencia sigue pendiente. Para empezar con bajo coste, se puede usar el escritorio con modelos locales mientras se reúne esa muestra. El primer despliegue alojado admite un único servidor con volumen persistente.

Se probó por separado el ejecutable de Windows con un perfil vacío. Sirvió los archivos de la interfaz, ejecutó Whisper y TitaNet-S incluidos, renderizó un MP4 de 1080 × 1920 con audio, produjo 48 entradas de subtítulos y duplicó el proyecto finalizado.
