"""
Bot de Discord para estadísticas de una liga/torneo de MOBAs.
Lee y escribe datos en una Google Sheet, y permite consultar
estadísticas (daño, daño recibido, curación, KDA, victorias...)
por jugador o por equipo, tanto de una jornada/torneo puntual
como acumuladas a lo largo de toda la liga.
"""

import os
import json
import statistics
from datetime import datetime
from typing import Optional, List, Dict

import discord
from discord import app_commands
from discord.ext import commands
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Puedes pasar las credenciales de dos formas:
# 1) GOOGLE_CREDS_JSON: el contenido completo del JSON pegado en una sola variable
#    de entorno (recomendado para Railway, así no subes el archivo a GitHub).
# 2) GOOGLE_CREDS_FILE: ruta a un archivo .json local (útil para correrlo en tu PC).
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
GOOGLE_CREDS_FILE = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")
SHEET_ID = os.getenv("SHEET_ID")
SHEET_TAB = os.getenv("SHEET_TAB", "Partidas")
ADMIN_ROLE_NAME = os.getenv("ADMIN_ROLE_NAME", "Staff")

# Columnas que el bot entiende. No hace falta que tu hoja las tenga TODAS ni en
# este orden exacto: el bot lee los encabezados reales de tu hoja y solo usa
# las columnas que existan. Si te falta alguna (ej. "Daño Recibido"), agrégala
# a tu hoja con este mismo nombre exacto y el bot empezará a usarla sola.
COLUMNAS_CONOCIDAS = [
    "Fecha", "ID Partida", "Jornada", "Juego", "Jugador", "Equipo", "Resultado",
    "Daño", "Daño Recibido", "Curación", "Kills", "Muertes", "Asistencias",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Cache simple para no golpear la API de Google en cada tecla del autocompletado
_jornadas_cache: List[str] = []
_equipos_cache: List[str] = []


def get_sheet():
    if GOOGLE_CREDS_JSON:
        info = json.loads(GOOGLE_CREDS_JSON)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)


def get_all_rows():
    """Lee todas las filas de la hoja, mapeadas por el nombre real de cada columna."""
    sheet = get_sheet()
    return sheet.get_all_records()


def campo(row: dict, nombre: str) -> str:
    """Acceso seguro a una columna: si tu hoja todavía no la tiene, devuelve vacío."""
    return str(row.get(nombre, "")).strip()


def refresh_caches(rows):
    global _jornadas_cache, _equipos_cache
    jornadas, equipos = [], []
    for r in rows:
        j = campo(r, "Jornada")
        e = campo(r, "Equipo")
        if j and j not in jornadas:
            jornadas.append(j)
        if e and e not in equipos:
            equipos.append(e)
    _jornadas_cache = jornadas
    _equipos_cache = equipos
    return jornadas, equipos


def is_staff(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    objetivo = ADMIN_ROLE_NAME.strip().lower()
    return any(role.name.strip().lower() == objetivo for role in interaction.user.roles)


def filtrar_por_jornada(rows, jornada: Optional[str]):
    if not jornada:
        return rows
    jornada_norm = jornada.strip().lower()
    return [r for r in rows if campo(r, "Jornada").lower() == jornada_norm]


def numeros(partidas, columna: str) -> List[float]:
    valores = []
    for p in partidas:
        v = campo(p, columna)
        if v != "":
            try:
                valores.append(float(v))
            except ValueError:
                pass
    return valores


def contar_victorias(partidas) -> int:
    """
    Cuenta victorias. Si las filas tienen 'ID Partida' cargado, cuenta partidas
    únicas ganadas (evita contar 5 veces la misma partida cuando hay 5 filas,
    una por jugador del equipo). Si no hay 'ID Partida', cuenta cada fila tal
    cual (comportamiento simple, útil si registras una fila por jugador y no
    te preocupa la duplicidad en el conteo de equipo).
    """
    con_id = [p for p in partidas if campo(p, "ID Partida") != ""]
    if con_id and len(con_id) == len(partidas):
        vistas_ganadas = set()
        for p in partidas:
            if campo(p, "Resultado").lower() in ("victoria", "win", "ganada"):
                vistas_ganadas.add(campo(p, "ID Partida"))
        return len(vistas_ganadas)
    return sum(1 for p in partidas if campo(p, "Resultado").lower() in ("victoria", "win", "ganada"))


def contar_partidas(partidas) -> int:
    """Igual que contar_victorias pero para el total de partidas (usa ID Partida si está)."""
    con_id = [p for p in partidas if campo(p, "ID Partida") != ""]
    if con_id and len(con_id) == len(partidas):
        return len({campo(p, "ID Partida") for p in partidas})
    return len(partidas)


def calcular_valor(partidas, metrica: str) -> Optional[float]:
    danos = numeros(partidas, "Daño")
    danos_recibidos = numeros(partidas, "Daño Recibido")
    curaciones = numeros(partidas, "Curación")
    kills = numeros(partidas, "Kills")
    muertes = numeros(partidas, "Muertes")
    asistencias = numeros(partidas, "Asistencias")

    if metrica == "dano_promedio" and danos:
        return statistics.mean(danos)
    if metrica == "dano_max" and danos:
        return max(danos)
    if metrica == "dano_total" and danos:
        return sum(danos)
    if metrica == "dano_recibido_promedio" and danos_recibidos:
        return statistics.mean(danos_recibidos)
    if metrica == "dano_recibido_total" and danos_recibidos:
        return sum(danos_recibidos)
    if metrica == "curacion_promedio" and curaciones:
        return statistics.mean(curaciones)
    if metrica == "curacion_total" and curaciones:
        return sum(curaciones)
    if metrica == "victorias":
        return float(contar_victorias(partidas))
    if metrica == "kda" and kills and muertes:
        return (sum(kills) + sum(asistencias)) / max(sum(muertes), 1)
    return None


METRICA_CHOICES = [
    app_commands.Choice(name="Daño promedio", value="dano_promedio"),
    app_commands.Choice(name="Daño más alto (una sola partida)", value="dano_max"),
    app_commands.Choice(name="Daño total acumulado", value="dano_total"),
    app_commands.Choice(name="Daño recibido promedio", value="dano_recibido_promedio"),
    app_commands.Choice(name="Daño recibido total", value="dano_recibido_total"),
    app_commands.Choice(name="Curación promedio", value="curacion_promedio"),
    app_commands.Choice(name="Curación total", value="curacion_total"),
    app_commands.Choice(name="Victorias", value="victorias"),
    app_commands.Choice(name="KDA promedio", value="kda"),
]


def agrupar_por(rows, campo_nombre: str) -> Dict[str, list]:
    grupos: Dict[str, list] = {}
    for r in rows:
        clave = campo(r, campo_nombre)
        if not clave:
            continue
        grupos.setdefault(clave, []).append(r)
    return grupos


def construir_embed_stats(nombre: str, tipo: str, jornada: Optional[str], partidas: list) -> discord.Embed:
    total = contar_partidas(partidas)
    victorias = contar_victorias(partidas)
    danos = numeros(partidas, "Daño")
    danos_recibidos = numeros(partidas, "Daño Recibido")
    curaciones = numeros(partidas, "Curación")
    kills = numeros(partidas, "Kills")
    muertes = numeros(partidas, "Muertes")
    asistencias = numeros(partidas, "Asistencias")

    titulo = f"Estadísticas de {nombre} ({tipo})"
    titulo += f" — {jornada}" if jornada else " — Toda la liga"

    embed = discord.Embed(title=titulo, color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.add_field(name="Partidas", value=str(total), inline=True)
    if total:
        embed.add_field(name="Victorias", value=f"{victorias} ({victorias/total*100:.1f}%)", inline=True)
        embed.add_field(name="Derrotas", value=str(total - victorias), inline=True)

    if danos:
        embed.add_field(name="Daño promedio", value=f"{statistics.mean(danos):,.0f}", inline=True)
        embed.add_field(name="Daño más alto", value=f"{max(danos):,.0f}", inline=True)
        embed.add_field(name="Daño total", value=f"{sum(danos):,.0f}", inline=True)

    if danos_recibidos:
        embed.add_field(name="Daño recibido promedio", value=f"{statistics.mean(danos_recibidos):,.0f}", inline=True)
        embed.add_field(name="Daño recibido total", value=f"{sum(danos_recibidos):,.0f}", inline=True)

    if curaciones:
        embed.add_field(name="Curación promedio", value=f"{statistics.mean(curaciones):,.0f}", inline=True)
        embed.add_field(name="Curación total", value=f"{sum(curaciones):,.0f}", inline=True)

    if kills and muertes and asistencias:
        kda = (sum(kills) + sum(asistencias)) / max(sum(muertes), 1)
        embed.add_field(name="KDA promedio", value=f"{kda:.2f}", inline=True)
        embed.add_field(
            name="K/D/A totales",
            value=f"{int(sum(kills))}/{int(sum(muertes))}/{int(sum(asistencias))}",
            inline=True,
        )

    return embed


intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Conectado como {bot.user}. {len(synced)} comandos sincronizados.")
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")


async def jornada_autocomplete(interaction: discord.Interaction, current: str):
    try:
        if not _jornadas_cache:
            refresh_caches(get_all_rows())
        return [app_commands.Choice(name=j, value=j) for j in _jornadas_cache if current.lower() in j.lower()][:25]
    except Exception:
        return []


async def equipo_autocomplete(interaction: discord.Interaction, current: str):
    try:
        if not _equipos_cache:
            refresh_caches(get_all_rows())
        return [app_commands.Choice(name=e, value=e) for e in _equipos_cache if current.lower() in e.lower()][:25]
    except Exception:
        return []


@bot.tree.command(name="stats", description="Muestra las estadísticas de un jugador")
@app_commands.describe(
    jugador="Nombre del jugador tal como aparece en la hoja",
    jornada="(Opcional) Filtra solo por una jornada/torneo específico. Si se omite, usa toda la liga.",
)
@app_commands.autocomplete(jornada=jornada_autocomplete)
async def stats(interaction: discord.Interaction, jugador: str, jornada: Optional[str] = None):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    rows = filtrar_por_jornada(rows, jornada)
    partidas = [r for r in rows if campo(r, "Jugador").lower() == jugador.strip().lower()]

    if not partidas:
        alcance = f" en **{jornada}**" if jornada else ""
        await interaction.followup.send(f"No encontré partidas registradas para **{jugador}**{alcance}.")
        return

    embed = construir_embed_stats(jugador, "jugador", jornada, partidas)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="stats_equipo", description="Muestra las estadísticas acumuladas de un equipo")
@app_commands.describe(
    equipo="Nombre del equipo tal como aparece en la hoja",
    jornada="(Opcional) Filtra solo por una jornada/torneo específico. Si se omite, usa toda la liga.",
)
@app_commands.autocomplete(equipo=equipo_autocomplete, jornada=jornada_autocomplete)
async def stats_equipo(interaction: discord.Interaction, equipo: str, jornada: Optional[str] = None):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    rows = filtrar_por_jornada(rows, jornada)
    partidas = [r for r in rows if campo(r, "Equipo").lower() == equipo.strip().lower()]

    if not partidas:
        alcance = f" en **{jornada}**" if jornada else ""
        await interaction.followup.send(f"No encontré partidas registradas para el equipo **{equipo}**{alcance}.")
        return

    embed = construir_embed_stats(equipo, "equipo", jornada, partidas)
    embed.set_footer(text="Nota: si no cargaste 'ID Partida', las victorias/partidas cuentan cada fila de jugador, no partidas únicas.")
    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="top",
    description="Ranking de jugadores. Sin 'jornada': toda la liga. Con 'jornada': solo esa fecha/torneo.",
)
@app_commands.describe(
    metrica="Métrica para ordenar el ranking",
    jornada="(Opcional) Solo esta jornada/torneo. Si se omite, se calcula con TODAS las jornadas acumuladas.",
)
@app_commands.choices(metrica=METRICA_CHOICES)
@app_commands.autocomplete(jornada=jornada_autocomplete)
async def top(interaction: discord.Interaction, metrica: app_commands.Choice[str], jornada: Optional[str] = None):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    refresh_caches(rows)
    rows = filtrar_por_jornada(rows, jornada)

    if jornada and not rows:
        await interaction.followup.send(f"No encontré partidas para la jornada **{jornada}**.")
        return

    grupos = agrupar_por(rows, "Jugador")
    resultados = [(nombre, v) for nombre, partidas in grupos.items()
                  if (v := calcular_valor(partidas, metrica.value)) is not None]

    if not resultados:
        await interaction.followup.send("No hay suficientes datos todavía para calcular ese ranking.")
        return

    resultados.sort(key=lambda x: x[1], reverse=True)
    medallas = ["🥇", "🥈", "🥉"]
    lineas = [f"{medallas[i] if i < 3 else f'{i+1}.'} **{n}** — {v:,.2f}" for i, (n, v) in enumerate(resultados[:10])]

    embed = discord.Embed(title=f"🏆 Ranking de jugadores: {metrica.name}", description="\n".join(lineas), color=discord.Color.gold())
    embed.set_footer(text=f"Jornada: {jornada}" if jornada else "Acumulado de toda la liga")
    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="top_equipo",
    description="Ranking de equipos. Sin 'jornada': toda la liga. Con 'jornada': solo esa fecha/torneo.",
)
@app_commands.describe(
    metrica="Métrica para ordenar el ranking",
    jornada="(Opcional) Solo esta jornada/torneo. Si se omite, se calcula con TODAS las jornadas acumuladas.",
)
@app_commands.choices(metrica=METRICA_CHOICES)
@app_commands.autocomplete(jornada=jornada_autocomplete)
async def top_equipo(interaction: discord.Interaction, metrica: app_commands.Choice[str], jornada: Optional[str] = None):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    refresh_caches(rows)
    rows = filtrar_por_jornada(rows, jornada)

    if jornada and not rows:
        await interaction.followup.send(f"No encontré partidas para la jornada **{jornada}**.")
        return

    grupos = agrupar_por(rows, "Equipo")
    resultados = [(nombre, v) for nombre, partidas in grupos.items()
                  if (v := calcular_valor(partidas, metrica.value)) is not None]

    if not resultados:
        await interaction.followup.send("No hay suficientes datos todavía para calcular ese ranking.")
        return

    resultados.sort(key=lambda x: x[1], reverse=True)
    medallas = ["🥇", "🥈", "🥉"]
    lineas = [f"{medallas[i] if i < 3 else f'{i+1}.'} **{n}** — {v:,.2f}" for i, (n, v) in enumerate(resultados[:10])]

    embed = discord.Embed(title=f"🏆 Ranking de equipos: {metrica.name}", description="\n".join(lineas), color=discord.Color.gold())
    embed.set_footer(text=f"Jornada: {jornada}" if jornada else "Acumulado de toda la liga")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="jornadas", description="Lista todas las jornadas/torneos registrados en la liga")
async def jornadas(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    lista, _ = refresh_caches(rows)
    if not lista:
        await interaction.followup.send("Todavía no hay ninguna jornada registrada.")
        return

    embed = discord.Embed(title="📅 Jornadas registradas", description="\n".join(f"• {j}" for j in lista), color=discord.Color.blurple())
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="mi_permiso", description="Muestra si el bot te reconoce como Staff/Admin en este servidor, y por qué")
async def mi_permiso(interaction: discord.Interaction):
    es_admin = interaction.user.guild_permissions.administrator
    roles = [r.name for r in interaction.user.roles if r.name != "@everyone"]
    tiene_rol_staff = any(r.strip().lower() == ADMIN_ROLE_NAME.strip().lower() for r in roles)

    lineas = [
        f"**Variable ADMIN_ROLE_NAME configurada:** `{ADMIN_ROLE_NAME}`",
        f"**Tus roles en este servidor:** {', '.join(roles) if roles else '(ninguno)'}",
        f"**¿Tienes permiso de Administrador?** {'Sí' if es_admin else 'No'}",
        f"**¿Tienes el rol Staff configurado?** {'Sí' if tiene_rol_staff else 'No'}",
        f"**¿Puedes usar /registrar?** {'Sí ✅' if (es_admin or tiene_rol_staff) else 'No ❌'}",
    ]
    await interaction.response.send_message("\n".join(lineas), ephemeral=True)


@bot.tree.command(name="registrar", description="(Staff) Registra una partida en la hoja de estadísticas")
@app_commands.describe(
    jornada="Jornada/torneo al que pertenece esta partida (ej: 'Jornada 1')",
    juego="Nombre del juego (ej: League of Legends, Dota 2, Smite)",
    jugador="Nombre del jugador",
    equipo="Equipo del jugador",
    resultado="Victoria o Derrota",
    dano="Daño hecho en la partida",
    kills="Kills en la partida",
    muertes="Muertes en la partida",
    asistencias="Asistencias en la partida",
    dano_recibido="(Opcional) Daño recibido en la partida",
    curacion="(Opcional) Curación hecha en la partida",
    id_partida="(Opcional pero recomendado) Un identificador igual para todos los jugadores de la MISMA partida, para que /top_equipo cuente victorias correctamente (ej: 'J1-P3')",
)
@app_commands.choices(resultado=[
    app_commands.Choice(name="Victoria", value="Victoria"),
    app_commands.Choice(name="Derrota", value="Derrota"),
])
@app_commands.autocomplete(jornada=jornada_autocomplete, equipo=equipo_autocomplete)
async def registrar(
    interaction: discord.Interaction,
    jornada: str,
    juego: str,
    jugador: str,
    equipo: str,
    resultado: app_commands.Choice[str],
    dano: float,
    kills: int,
    muertes: int,
    asistencias: int,
    dano_recibido: Optional[float] = None,
    curacion: Optional[float] = None,
    id_partida: Optional[str] = None,
):
    if not is_staff(interaction):
        await interaction.response.send_message("Solo el staff puede registrar partidas.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        sheet = get_sheet()
        fecha = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        datos = {
            "Fecha": fecha,
            "ID Partida": id_partida or "",
            "Jornada": jornada,
            "Juego": juego,
            "Jugador": jugador,
            "Equipo": equipo,
            "Resultado": resultado.value,
            "Daño": dano,
            "Daño Recibido": dano_recibido if dano_recibido is not None else "",
            "Curación": curacion if curacion is not None else "",
            "Kills": kills,
            "Muertes": muertes,
            "Asistencias": asistencias,
        }
        headers = sheet.row_values(1)
        fila = [str(datos.get(h, "")) for h in headers]
        sheet.append_row(fila)
        await interaction.followup.send(
            f"✅ Partida registrada: **{jugador}** ({equipo}) — {jornada}, {resultado.value}, "
            f"daño {dano:,.0f}, KDA {kills}/{muertes}/{asistencias}."
        )
    except Exception as e:
        await interaction.followup.send(f"Error al guardar en la hoja: {e}")


if __name__ == "__main__":
    if not DISCORD_TOKEN or not SHEET_ID:
        raise SystemExit("Faltan variables de entorno. Revisa DISCORD_TOKEN y SHEET_ID en tu archivo .env")
    bot.run(DISCORD_TOKEN)
