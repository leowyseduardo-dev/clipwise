# Publicación automática

Clipwise puede subir cada clip renderizado a un canal de YouTube o a una cuenta
de TikTok. Abre el clip y elige **Publicar en YouTube** o **Publicar en TikTok**;
la primera vez, configura credenciales y conecta la cuenta desde la misma ventana.

## Datos locales

- Las credenciales de la app OAuth se guardan en `DATA_DIR/publishing.json`.
- Los tokens OAuth y el historial de subidas se guardan en la base SQLite local.
- Los secretos no se devuelven a la interfaz después de guardarlos; un campo vacío
  conserva el secreto existente.
- La subida usa el MP4 renderizado localmente y no envía el archivo a un servicio
  de terceros distinto de la plataforma elegida.

## YouTube

1. En [Google Cloud Console](https://console.cloud.google.com/), crea o selecciona
   un proyecto y habilita **YouTube Data API v3**.
2. Configura la pantalla de consentimiento OAuth y crea un cliente OAuth de tipo
   **Aplicación de escritorio**.
3. Copia el Client ID y Client Secret en **Ajustes → Credenciales de publicación**
   de Clipwise. También puedes definir `YOUTUBE_CLIENT_ID` y
   `YOUTUBE_CLIENT_SECRET` en el entorno.
4. Conecta el canal desde la pestaña YouTube. Clipwise solicita los alcances
   `youtube.upload` y `youtube.readonly`.

Las subidas se crean con la privacidad elegida en los ajustes (por defecto,
**privado**). YouTube Data API consume 1600 unidades de cuota por `videos.insert`;
la cuota diaria predeterminada de 10 000 unidades permite aproximadamente seis
subidas al día.

## TikTok

1. Registra una aplicación en [TikTok for Developers](https://developers.tiktok.com/)
   y activa **Login Kit** y **Content Posting API**.
2. Habilita el alcance `video.publish` y completa la revisión/aprobación necesaria
   para publicar mediante Direct Post.
3. Registra la Redirect URI que muestra Clipwise en los ajustes. Copia el Client
   Key y Client Secret en Clipwise, y conecta la cuenta desde la pestaña TikTok.
4. Elige una privacidad admitida por la cuenta. Clipwise usa Direct Post, sube el
   archivo por fragmentos y consulta el estado hasta que TikTok confirme el post.

La Redirect URI predeterminada es `http://127.0.0.1:53682/oauth/callback`. Si la
configuración de TikTok exige `localhost`, define
`PUBLISHING_REDIRECT_HOST=localhost` y registra la URI exacta que aparece en la
interfaz. Si el puerto está ocupado, cambia `PUBLISHING_REDIRECT_PORT` o el puerto
en los ajustes y vuelve a registrar la URI. El servidor de callback solo acepta
hosts loopback.

## Privacidad y límites

- La privacidad predeterminada es privada en ambas plataformas; verifica la
  selección antes de publicar.
- TikTok puede limitar Direct Post a cuentas/app revisadas, formatos, duración,
  frecuencia o valores de privacidad disponibles para esa cuenta.
- Clipwise guarda tokens localmente para renovar sesiones; desconectar una
  plataforma elimina sus tokens locales.
- Las plataformas pueden tardar en procesar el video. El panel muestra el estado,
  avance, errores y enlace disponible cuando termina.
