# Clipwise 24/7 gratis en Google Cloud (alternativa a Oracle)

Mismo Docker, mismo Caddy, misma web con clips. Cambia solo el proveedor de la VM.

- **VM**: Compute Engine **e2-micro**, 0.25 vCPU compartida / 1 GB RAM / 30 GB disco.
- **Coste**: $0 mientras la cuenta exista, en regiones `us-west1`, `us-central1` o `us-east1`.
- **Requiere**: cuenta de Google Cloud con facturación activada (tarjeta). El nivel always-free
  no cobra, pero Active las alertas de presupuesto por si sale del tier.
- **Tráfico**: 1 GB/mes de salida desde Norteamérica incluido. Sirve para un MVP; vigila el
  consumo si publicas muchos clips.

> Con 1 GB de RAM el swap es obligatorio para compilar el frontend dentro de Docker.

## 1. Crear el proyecto

1. Entra a `https://console.cloud.google.com/` e inicia sesión.
2. Acepta los términos y **activa la facturación** (necesitas tarjeta).
3. Crea un proyecto, por ejemplo `clipwise-prod`.
4. En **APIs y servicios → Biblioteca**, busca y habilita **Compute Engine API**.

## 2. Crear la VM

1. **Compute Engine → Instancias de VM → Crear instancia**.
2. Configura:
   - **Nombre**: `clipwise`
   - **Región**: `us-west1` (Oregón), `us-central1` (Iowa) o `us-east1` (Carolina del Sur).
     Solo estas regiones tienen e2-micro en el tier gratuito.
   - **Zona**: cualquiera de esa región, p. ej. `us-west1-b`.
   - **Tipo de máquina**: **e2-micro** (debe decir *Elegible para nivel gratuito*).
   - **Disco de arranque**: **Ubuntu 24.04 LTS**, 30 GB (estándar).
   - **Firewall**: marca **Permitir tráfico HTTP** y **Permitir tráfico HTTPS**.
3. Pulsa **Crear**. Copia la **IP externa** que aparece.

Si no marcaste el firewall: **Redes de VPC → Firewall → Crear regla de firewall**:
- `tcp:80` y `tcp:443`, origen `0.0.0.0/0`, aplicable a todas las instancias.

## 3. Conectar e instalar Docker

En la fila de la VM, pulsa el botón **SSH** (abre una terminal en el navegador; no necesitas
clave propia).

Dentro:

```bash
sudo apt-get update && sudo apt-get install -y git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
docker --version
docker compose version
```

Crea swap (obligatorio con 1 GB):

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Cierra la terminal SSH y vuelve a abrirla para que el grupo `docker` aplique.

## 4. Traer el código

El repo es público, así que no hace falta subir archivos desde Windows:

```bash
sudo git clone https://github.com/leowyseduardo-dev/clipwise.git /opt/clipwise
sudo chown -R $USER:$USER /opt/clipwise
cd /opt/clipwise
```

Si quieres actualizar después:

```bash
cd /opt/clipwise && git pull && docker compose up -d --build
```

## 5. Configurar

```bash
cp .env.production.example .env.production
nano .env.production
```

Cambia:

```env
APP_DOMAIN=app.TU_IP_EXTERNA.sslip.io
CLIPFORGE_PUBLIC_ORIGIN=https://app.TU_IP_EXTERNA.sslip.io
PAYPAL_CLIENT_ID=BAAFvUUXDGuhU_4L6MWlDXs4PGXU6gD-OP2v-y_EkUlGvcMCrAcKjRDlPHZdgvWy7l0vAd5bsHQJJ9FqIM
PAYPAL_CLIENT_SECRET=TU_SECRETO_DE_PAYPAL
PAYPAL_MODE=live
PAYPAL_PRODUCT_ID=PROD-0VJ49900FS465031M
PAYPAL_CREATOR_PLAN_ID=P-9JK82163JY201791BNMCPAMA
PAYPAL_STUDIO_PLAN_ID=P-73R478908B315820HNMCPAMI
PAYPAL_PUBLIC_URL=https://app.TU_IP_EXTERNA.sslip.io
PAYPAL_WEBHOOK_ID=
CLIPFORGE_ADMIN_PASSWORD=TU_CLAVE_REAL
WHISPER_MODEL=small
```

Con 1 GB de RAM usa `WHISPER_MODEL=small`. Si algún día pasas a una máquina más grande,
puedes subir a `medium` o `large-v3`.

## 6. Levantar y verificar

```bash
docker compose up -d --build
docker compose logs -f app
```

El primer build con 1 GB + swap tarda bastante; es normal.

Verifica:

```bash
curl -I https://app.TU_IP_EXTERNA.sslip.io
curl https://app.TU_IP_EXTERNA.sslip.io/api/public/config
```

Debe devolver `"paypal":{"configured":true,...}`. Si el webhook no se creó solo, llama
a `POST /api/admin/paypal/setup` con la sesión de administrador.

## 7. Administrar

Entra a `https://app.TU_IP_EXTERNA.sslip.io`, inicia sesión con
`Leowysgarcia@gmail.com` y la clave del paso 5. Los pagos de Creator y Studio se
activan solos con PayPal. **Mi cuenta → Admin → Activar plan manual** queda como
respaldo para casos especiales.

## 8. Límites y consejos

- 1 GB de RAM: con swap funciona, pero los builds son lentos. No levantes más de un workspace
  (`CLIPFORGE_MAX_WORKSPACES=1` recomendado).
- 1 GB/mes de tráfico saliente gratis: pon una alerta de facturación en GCP.
- El puerto 22 no hace falta abrirlo más de lo que ya está; usas el SSH del navegador.
- Si el build muere por memoria, aumenta el swap a 8 GB.

## 9. Otras alternativas (resumen)

| Opción | 24/7 real | Render con FFmpeg | Dificultad |
|---|---|---|---|
| **GCP e2-micro** (esta guía) | Sí | Sí, en el VPS | Baja: reuse el Docker |
| Google Cloud Run | No (scale-to-zero) | Sí, hasta 60 min | Media: hay que partir la app en jobs |
| Modal ($30/mes crédito) | No (bajo demanda) | Sí | Alta: reescribir el motor como funciones |
| Render / Koyeb / HF Spaces | No, duermen | Limitado | Media |
| Vercel + Turso + R2 | Web sí, motor no | No | Media |
