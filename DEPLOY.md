# Clipwise — despliegue 24/7 gratis (VPS + Docker + Caddy)

Stack: **Vercel no puede renderizar clips en su plan gratis** (funciones de 10 s y sin
filesystem). Aquí la página web, la API y el motor FFmpeg + Whisper viven en un mismo
VPS siempre encendido. El usuario sigue usando una página web: pega un enlace y recibe
clips. No instala nada.

- Docker + Compose: un contenedor con la web compilada, la API cloud y los motores por equipo.
- Caddy: HTTPS automático con Let's Encrypt.
- SQLite persistente en un volumen: cuentas, sesiones, trabajos y clips.
- Opcional: Groq como LLM para elegir los mejores momentos desde la transcripción.

> Una sola instancia. No levantar réplicas: SQLite y los workspaces son un volumen local.

## 1. Crear la cuenta y la VM en Oracle

1. Regístrate en `https://www.oracle.com/cloud/free/`. Pide tarjeta de crédito, pero el
   nivel **Always Free** no cobra mientras no excedas los límites.
2. En la consola: **Compute → Instances → Create Instance**.
   - Name: `clipwise`.
   - Image: **Ubuntu 24.04** (Canonical).
   - Shape: **Ampere A1 (ARM)**, 4 OCPU / 24 GB (Always Free). Si no hay capacidad en tu
     región, usa `VM.Standard.E2.1.Micro` (1/8 OCPU / 1 GB) y añade swap.
   - SSH key: genera una en tu Windows:
     ```powershell
     ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\clipwise_key
     ```
     Pega el contenido de `clipwise_key.pub` en el campo **Public SSH key**.
   - Pulsa **Create**.
3. Copia la **Public IP** de la instancia.

## 2. Abrir los puertos 80 y 443

En la consola: **Networking → Virtual Cloud Networks → tu VCN → Security Lists →
Default Security List → Ingress Rules → Add Ingress Rules**:

- Source CIDR `0.0.0.0/0`, Destination Port Range `80`, Protocol `TCP`.
- Source CIDR `0.0.0.0/0`, Destination Port Range `443`, Protocol `TCP`.

El puerto 22 ya suele estar abierto. Comprueba además el firewall del sistema:

```bash
sudo ufw status
```

Si está activo: `sudo ufw allow 80 && sudo ufw allow 443`.

## 3. Conectar e instalar Docker

Desde PowerShell en tu máquina:

```powershell
ssh -i $env:USERPROFILE\.ssh\clipwise_key ubuntu@TU_IP
```

Dentro del VPS:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
docker --version
docker compose version
```

Si la VM tiene 1 GB de RAM, crea swap antes del build:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Sal (`exit`) y vuelve a entrar para que el grupo `docker` tenga efecto.

## 4. Subir el proyecto

Desde PowerShell en tu máquina:

```powershell
scp -i $env:USERPROFILE\.ssh\clipwise_key -r C:\Users\leoca\OneDrive\Desktop\XD\clipforge ubuntu@TU_IP:~/clipwise
```

Dentro del VPS:

```bash
sudo mkdir -p /opt
sudo mv ~/clipwise /opt/clipwise
sudo chown -R ubuntu:ubuntu /opt/clipwise
cd /opt/clipwise
```

No hace falta subir `node_modules`, `web/dist`, `.git`, `engine/.env`, `.env.production`
ni `desktop/dist`: Docker compila el frontend dentro de la imagen y las claves se ponen
en `.env.production`.

## 5. Configurar y levantar

```bash
cp .env.production.example .env.production
nano .env.production
```

Mínimo imprescindible:

- `APP_DOMAIN`: `app.TU_IP.sslip.io` (o tu dominio).
- `CLIPFORGE_PUBLIC_ORIGIN`: la misma URL con `https://`.
- `PAYPAL_ME_URL`: `https://paypal.me/TenderMarginAI`.
- `CLIPFORGE_ADMIN_PASSWORD`: la clave real del administrador (nunca la deje en el ejemplo).
- `WHISPER_MODEL`: `medium` o `large-v3` para máxima calidad; `small` si el VPS es corto de CPU.

Levantar:

```bash
docker compose up -d --build
docker compose logs -f app
```

El primer build tarda varios minutos. El primer trabajo descarga el modelo de Whisper a
`/data/models` (volumen `clipwise_data`); puede tardar un poco más.

Verificar:

```bash
curl -I https://TU_DOMINIO
curl https://TU_DOMINIO/api/public/config
```

Debe devolver `{"paypal_me":"https://paypal.me/TenderMarginAI"}`.

## 6. Administrar planes

1. Abra `https://TU_DOMINIO` e inicie sesión con `CLIPFORGE_ADMIN_EMAIL` y
   `CLIPFORGE_ADMIN_PASSWORD`.
2. **Mi cuenta → Admin → Activar plan manual**: ahí activa Creator/Studio cuando
   reciba un pago en PayPal.
3. El seed del administrador es idempotente: si el usuario ya existe, solo asegura que
   su equipo quede en Studio. Si quiere desactivarlo, ponga `CLIPFORGE_SEED_ADMIN=0` y
   reinicie.

## 7. Groq opcional (mejores momentos, no render)

El motor ya lee `LLM_API_KEY`, `LLM_BASE_URL` y `LLM_MODEL`. Para usar Groq como LLM:

```env
LLM_API_KEY=TU_CLAVE_DE_GROQ
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

Groq **no descarga ni renderiza vídeo**: solo analiza la transcripción. El corte,
reencuadre, subtitulado y exportación los hace FFmpeg. Consulte en
`console.groq.com` los modelos disponibles si cambia el nombre.

La transcripción sigue siendo local con faster-whisper. Conectar la API de
Whisper de Groq requiere código adicional; hoy no está cableada.

## 8. YouTube con verificación

Si YouTube pide cookies, monte un archivo Netscape y añada al `docker-compose.yml`:

```yaml
    volumes:
      - clipwise_data:/data
      - ./cookies.txt:/data/cookies.txt:ro
```

Y en `.env.production`:

```env
YTDLP_COOKIES=/data/cookies.txt
```

## 9. Operación diaria

```bash
docker compose logs -f app      # logs
docker compose restart          # reiniciar
docker compose down             # detener (los datos quedan en el volumen)
docker compose up -d --build    # actualizar tras subir cambios
```

## 10. Backups

```bash
mkdir -p backups
docker run --rm -v clipwise_data:/data -v "$(pwd)/backups:/backup" alpine \
  tar czf "/backup/clipwise-$(date +%F).tar.gz" -C /data .
```

Copie `backups/` fuera del VPS (rclone, S3, otro servidor). El volumen `clipwise_data`
contiene la base de datos, los workspaces y los modelos: no lo borre.

## 11. Actualizar desde GitHub

```bash
cd /opt/clipwise
git pull
docker compose up -d --build
```

## 12. Límites conocidos

- Un solo proceso: SQLite no soporta varias instancias escribiendo el mismo archivo.
- CPU sola: `large-v3` da mejor transcripción pero es lento; `medium` es el equilibrio.
- En ARM, si `pip install` falla para `ctranslate2`, use una VM x86 del free tier o
  construya con `--platform linux/amd64` (más lento).
- Vercel + Turso + R2 sirven para una web estática y metadata, pero **no** para
  renderizar clips gratis: sus funciones mueren a los 10 s.
