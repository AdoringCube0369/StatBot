# Bot de estadísticas para liga de MOBAs

Bot de Discord que lee y escribe estadísticas de partidas (daño, KDA, victorias, etc.)
en una Google Sheet, para cualquier MOBA, con partidas personalizadas, organizadas
en jornadas o torneos a lo largo de una liga.

## El concepto clave: "Jornada"

Cada partida se registra bajo una **Jornada** (el nombre que le des a esa fecha o
torneo, ej: `"Jornada 1"`, `"Torneo Apertura - J3"`, `"Playoffs"`...). Esto es lo que
permite separar dos preguntas distintas:

- **"¿Quién hizo más daño EN esta jornada/torneo?"** → usas el comando con el
  parámetro `jornada` puesto.
- **"¿Quién ha hecho más daño ACUMULADO en toda la liga (todas las jornadas)?"**
  → usas el mismo comando pero SIN poner `jornada` — se calcula con todo el historial.

## Comandos

**Por jugador:**
- `/stats jugador:<nombre> jornada:<opcional>` — estadísticas de un jugador.
  Sin `jornada`, muestra el acumulado de toda la liga. Con `jornada`, solo esa fecha/torneo.
- `/top metrica:<...> jornada:<opcional>` — ranking top 10 de jugadores.

**Por equipo:**
- `/stats_equipo equipo:<nombre> jornada:<opcional>` — estadísticas acumuladas de un equipo completo.
- `/top_equipo metrica:<...> jornada:<opcional>` — ranking top 10 de equipos.

**Ambos rankings (`/top` y `/top_equipo`):**
  - **Sin `jornada`**: ranking acumulado de toda la liga (ideal para el premio a fin de temporada).
  - **Con `jornada`**: ranking solo de esa fecha/torneo puntual (ideal para el MVP de la jornada).
  - Métricas disponibles: daño promedio, daño más alto en una sola partida, daño total
    acumulado, daño recibido promedio, daño recibido total, curación promedio,
    curación total, victorias, KDA promedio.

**Utilidades:**
- `/jornadas` — lista todas las jornadas/torneos que ya tienen partidas registradas
  (útil para saber qué nombres escribir en los otros comandos; además hay autocompletado).
- `/registrar` — (solo Staff/Admins) carga una partida nueva directo desde Discord,
  indicando a qué jornada, equipo, daño, daño recibido y curación pertenece.

## Paso 1: Crear la Google Sheet

1. Crea una hoja de cálculo nueva en Google Sheets.
2. Ponle de nombre a la primera pestaña `Partidas` (o el nombre que prefieras, y ajusta `SHEET_TAB`).
3. En la fila 1, escribe exactamente estos encabezados, uno por columna:

   ```
   Fecha | ID Partida | Jornada | Juego | Jugador | Equipo | Resultado | Daño | Daño Recibido | Curación | Kills | Muertes | Asistencias
   ```

   El bot lee los encabezados por **nombre**, no por posición — puedes reordenar
   las columnas o quitar las que no uses (ej: si no te interesa "Curación", puedes
   omitirla) sin que se rompa nada. Si ya tenías una hoja de una versión anterior
   sin "ID Partida", "Daño Recibido" o "Curación", solo agrega las columnas nuevas
   con estos nombres exactos y el bot las empezará a usar automáticamente.
4. **"ID Partida"** (recomendada si te importan las estadísticas por equipo):
   ponle el mismo identificador a todos los jugadores de una misma partida
   (ej: `J1-P3` para la partida 3 de la Jornada 1). Sin esto, `/stats_equipo` y
   `/top_equipo` cuentan cada fila de jugador por separado al contar victorias —
   si tu equipo tiene 5 jugadores, una victoria del equipo sumaría 5 en vez de 1.
   Con "ID Partida" cargado, el bot detecta que esas 5 filas son la misma partida
   y cuenta solo 1 victoria por equipo.
5. En la columna "Jornada" escribe el nombre de la fecha o torneo al que pertenece
   esa partida (ej: `Jornada 1`, `Jornada 2`, `Torneo Apertura - J3`...). Usa el
   **mismo texto exacto** para todas las partidas de una misma jornada, o el bot
   las va a contar como jornadas distintas.
6. En la columna "Resultado" usa siempre "Victoria" o "Derrota" (el bot los reconoce en minúsculas también).
7. Copia el ID de la hoja desde la URL:
   `https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit` → ese es tu `SHEET_ID`.


## Paso 2: Crear credenciales de Google (cuenta de servicio)

1. Ve a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto nuevo (o usa uno existente).
3. Activa las APIs **Google Sheets API** y **Google Drive API**.
4. Ve a "Credenciales" → "Crear credenciales" → "Cuenta de servicio".
5. Una vez creada, entra a la cuenta de servicio → pestaña "Claves" → "Agregar clave" → JSON.
6. Se descargará un archivo `.json`. Renómbralo a `credentials.json` y ponlo en la misma carpeta que `bot.py`.
7. Abre ese archivo JSON y copia el valor de `client_email` (algo como `xxxx@xxxx.iam.gserviceaccount.com`).
8. Ve a tu Google Sheet → botón "Compartir" → pega ese email y dale permiso de **Editor**.
   (Esto es obligatorio: sin compartir la hoja con ese email, el bot no podrá leerla ni escribirla.)
9. **Para correrlo en tu PC**: deja el archivo como `credentials.json` junto a `bot.py`.
   **Para desplegarlo en Railway**: no subas ese archivo a GitHub — más abajo, en la
   sección de despliegue, se explica cómo pasarlo como variable de entorno.

## Paso 3: Crear el bot de Discord

1. Ve a [Discord Developer Portal](https://discord.com/developers/applications) → "New Application".
2. Ve a la pestaña "Bot" → "Add Bot".
3. Copia el "Token" (botón "Reset Token" si no lo ves) → ese es tu `DISCORD_TOKEN`.
4. Ve a "OAuth2" → "URL Generator". Marca los scopes `bot` y `applications.commands`.
   En permisos de bot marca al menos "Send Messages" y "Use Slash Commands".
5. Copia la URL generada, ábrela en el navegador, y añade el bot a tu servidor.

## Paso 4: Instalar y correr el bot

```bash
# Instala las dependencias
pip install -r requirements.txt

# Copia la plantilla de configuración y rellénala
cp .env.example .env
# Edita .env con tu DISCORD_TOKEN y SHEET_ID

# Corre el bot
python bot.py
```

Si todo está bien configurado, en la consola verás:
```
Conectado como TuBot#1234. 3 comandos sincronizados.
```

Los comandos `/stats`, `/top` y `/registrar` pueden tardar hasta una hora en
aparecer en Discord la primera vez (a veces son instantáneos). Si no aparecen,
reinicia Discord.

## Ejemplos de uso para la liga

**Premiar al que más daño hizo en una jornada puntual:**
```
/top metrica:Daño más alto (una sola partida) jornada:Jornada 3
```

**Premiar al que más daño acumuló en toda la liga (todas las jornadas juntas):**
```
/top metrica:Daño total acumulado
```
(sin poner nada en `jornada` — así toma todo el historial)

**Ver cómo le fue a un jugador solo en los playoffs:**
```
/stats jugador:NombreDelJugador jornada:Playoffs
```

**Ver el rendimiento acumulado de ese mismo jugador en toda la liga:**
```
/stats jugador:NombreDelJugador
```

**Premiar al equipo que más curó/tankeó daño en toda la liga:**
```
/top_equipo metrica:Curación total
/top_equipo metrica:Daño recibido total
```

**Ver el resumen completo de un equipo en la Jornada 2:**
```
/stats_equipo equipo:NombreDelEquipo jornada:Jornada 2
```

## Subirlo a GitHub

1. Crea un repositorio nuevo en GitHub (puede ser privado, no hace falta que sea público).
2. Desde la carpeta del proyecto:

   ```bash
   git init
   git add .
   git commit -m "Bot de estadísticas de liga"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
   git push -u origin main
   ```

   El `.gitignore` ya incluido evita que subas por error tu `.env` o `credentials.json`.
   **Nunca subas esos archivos a GitHub**, ni siquiera a un repo privado.

## Desplegarlo en Railway

1. Ve a [railway.app](https://railway.app) e inicia sesión con tu cuenta de GitHub.
2. Click en "New Project" → "Deploy from GitHub repo" → selecciona tu repositorio.
3. Railway va a detectar que es un proyecto Python automáticamente e instalará
   lo de `requirements.txt`. Gracias al `Procfile` incluido, sabrá que debe
   correrlo como un **worker** (proceso de fondo), no como un sitio web.
4. Ve a la pestaña **"Variables"** del proyecto en Railway y agrega estas:

   | Variable | Valor |
   |---|---|
   | `DISCORD_TOKEN` | tu token del bot |
   | `SHEET_ID` | el ID de tu Google Sheet |
   | `SHEET_TAB` | `Partidas` (o el nombre que uses) |
   | `ADMIN_ROLE_NAME` | `Staff` (o el que prefieras) |
   | `GOOGLE_CREDS_JSON` | el contenido **completo** del archivo `credentials.json`, pegado tal cual (ver paso 5) |

5. Para `GOOGLE_CREDS_JSON`: abre tu archivo `credentials.json` con un editor de texto,
   copia **todo** el contenido (empieza con `{"type": "service_account", ...}`) y
   pégalo como valor de esa variable en Railway, en una sola línea. No necesitas
   subir el archivo en sí — el bot ya está preparado para leer las credenciales
   desde esta variable si está presente.
6. Guarda las variables. Railway va a redesplegar el proyecto automáticamente.
7. Revisa la pestaña **"Deployments" → "View Logs"**. Deberías ver:
   ```
   Conectado como TuBot#1234. 4 comandos sincronizados.
   ```
   Si ves ese mensaje, el bot ya está corriendo 24/7.

### Actualizar el bot después

Cada vez que quieras cambiar algo del código, solo necesitas hacer:
```bash
git add .
git commit -m "descripción del cambio"
git push
```
Railway detecta el push y vuelve a desplegar automáticamente.

### Costos

Railway tiene un plan gratuito con horas limitadas al mes; para un bot que corre
24/7 probablemente necesites su plan de pago (unos pocos dólares al mes), ya que
el uso constante consume esas horas rápido. Revisa su página de precios actual
antes de decidir.

## Notas importantes

- El campo "Staff" en `/registrar` se controla con el rol de Discord `Staff`
  (puedes cambiar el nombre en `.env` con `ADMIN_ROLE_NAME`), o con cualquiera
  que tenga permiso de Administrador en el servidor.
- Si prefieres seguir cargando los datos directo en la Google Sheet en vez de
  usar `/registrar`, el bot igual va a leerlos sin problema — `/registrar` es
  solo una comodidad opcional.
- Puedes agregar más columnas a la hoja (ej: "Campeón/Héroe usado") sin romper
  nada; el bot solo usa las columnas que ya conoce.
