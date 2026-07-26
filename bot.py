"""
Bot de Discord para estadísticas de una liga/torneo de MOBAs.
Lee y escribe datos en una Google Sheet, y permite consultar
estadísticas (media de daño, daño más alto, victorias, etc.)
tanto por jornada/torneo individual como acumuladas a lo largo
de toda la liga, directamente desde Discord con comandos slash.
"""

import os
import json
import statistics
from datetime import datetime
from typing import Optional, List

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

# Columnas esperadas en la hoja (en este orden exacto en la fila 1).
# "Jornada" identifica la fecha/torneo/ronda de la liga (ej: "Jornada 1",
# "Torneo Apertura - J3", etc). Es lo que permite separar "mejor de esta
# jornada" de "mejor acumulado en toda la liga".
COLUMNS = [
    "Fecha", "Jornada", "Juego", "Jugador", "Equipo", "Resultado",
    "Daño", "Kills", "Muertes", "Asistencias",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Cache simple para no golpear la API de Google en cada tecla del autocompletado
_jornadas_cache: List[str] = []


def get_sheet():
    if GOOGLE_CREDS_JSON:
        info = json.loads(GOOGLE_CREDS_JSON)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)


def get_all_rows():
    sheet = get_sheet()
    records = sheet.get_all_records(expected_headers=COLUMNS)
    return records


def refresh_jornadas_cache(rows) -> List[str]:
    global _jornadas_cache
    vistas = []
    for r in rows:
        j = str(r.get("Jornada", "")).strip()
        if j and j not in vistas:
            vistas.append(j)
    _jornadas_cache = vistas
    return vistas


def is_staff(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    return any(role.name == ADMIN_ROLE_NAME for role in interaction.user.roles)


def filtrar_por_jornada(rows, jornada: Optional[str]):
    if not jornada:
        return rows
    jornada_norm = jornada.strip().lower()
    return [r for r in rows if str(r.get("Jornada", "")).strip().lower() == jornada_norm]


def calcular_valor(partidas, metrica: str) -> Optional[float]:
    """Calcula el valor de una métrica para un conjunto de partidas de un jugador."""
    danos = [float(p["Daño"]) for p in partidas if str(p["Daño"]).strip() != ""]
    kills = [float(p["Kills"]) for p in partidas if str(p["Kills"]).strip() != ""]
    muertes = [float(p["Muertes"]) for p in partidas if str(p["Muertes"]).strip() != ""]
    asistencias = [float(p["Asistencias"]) for p in partidas if str(p["Asistencias"]).strip() != ""]
    victorias = sum(1 for p in partidas if str(p["Resultado"]).strip().lower() in ("victoria", "win", "ganada"))

    if metrica == "dano_promedio" and danos:
        return statistics.mean(danos)
    if metrica == "dano_max" and danos:
        return max(danos)
    if metrica == "dano_total" and danos:
        return sum(danos)
    if metrica == "victorias":
        return float(victorias)
    if metrica == "kda" and kills and muertes:
        return (sum(kills) + sum(asistencias)) / max(sum(muertes), 1)
    return None


METRICA_CHOICES = [
    app_commands.Choice(name="Daño promedio", value="dano_promedio"),
    app_commands.Choice(name="Daño más alto (una sola partida)", value="dano_max"),
    app_commands.Choice(name="Daño total acumulado", value="dano_total"),
    app_commands.Choice(name="Victorias", value="victorias"),
    app_commands.Choice(name="KDA promedio", value="kda"),
]


intents = discord.Intents.default()
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
            rows = get_all_rows()
            refresh_jornadas_cache(rows)
        opciones = [j for j in _jornadas_cache if current.lower() in j.lower()]
        return [app_commands.Choice(name=j, value=j) for j in opciones[:25]]
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
    partidas = [r for r in rows if str(r["Jugador"]).strip().lower() == jugador.strip().lower()]

    if not partidas:
        alcance = f" en **{jornada}**" if jornada else ""
        await interaction.followup.send(f"No encontré partidas registradas para **{jugador}**{alcance}.")
        return

    total = len(partidas)
    victorias = sum(1 for p in partidas if str(p["Resultado"]).strip().lower() in ("victoria", "win", "ganada"))
    danos = [float(p["Daño"]) for p in partidas if str(p["Daño"]).strip() != ""]
    kills = [float(p["Kills"]) for p in partidas if str(p["Kills"]).strip() != ""]
    muertes = [float(p["Muertes"]) for p in partidas if str(p["Muertes"]).strip() != ""]
    asistencias = [float(p["Asistencias"]) for p in partidas if str(p["Asistencias"]).strip() != ""]

    titulo = f"Estadísticas de {jugador}"
    if jornada:
        titulo += f" — {jornada}"
    else:
        titulo += " — Toda la liga"

    embed = discord.Embed(title=titulo, color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.add_field(name="Partidas jugadas", value=str(total), inline=True)
    embed.add_field(name="Victorias", value=f"{victorias} ({victorias/total*100:.1f}%)", inline=True)
    embed.add_field(name="Derrotas", value=str(total - victorias), inline=True)

    if danos:
        embed.add_field(name="Daño promedio", value=f"{statistics.mean(danos):,.0f}", inline=True)
        embed.add_field(name="Daño más alto", value=f"{max(danos):,.0f}", inline=True)
        embed.add_field(name="Daño total", value=f"{sum(danos):,.0f}", inline=True)

    if kills and muertes and asistencias:
        kda = (sum(kills) + sum(asistencias)) / max(sum(muertes), 1)
        embed.add_field(name="KDA promedio", value=f"{kda:.2f}", inline=True)
        embed.add_field(
            name="K/D/A totales",
            value=f"{int(sum(kills))}/{int(sum(muertes))}/{int(sum(asistencias))}",
            inline=True,
        )

    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="top",
    description="Ranking de la liga. Sin 'jornada': acumulado de toda la liga. Con 'jornada': solo esa fecha/torneo.",
)
@app_commands.describe(
    metrica="Métrica para ordenar el ranking",
    jornada="(Opcional) Solo esta jornada/torneo. Si se omite, se calcula con TODAS las jornadas acumuladas.",
)
@app_commands.choices(metrica=METRICA_CHOICES)
@app_commands.autocomplete(jornada=jornada_autocomplete)
async def top(
    interaction: discord.Interaction,
    metrica: app_commands.Choice[str],
    jornada: Optional[str] = None,
):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    refresh_jornadas_cache(rows)
    rows = filtrar_por_jornada(rows, jornada)

    if jornada and not rows:
        await interaction.followup.send(f"No encontré partidas para la jornada **{jornada}**.")
        return

    jugadores = {}
    for r in rows:
        nombre = str(r["Jugador"]).strip()
        if not nombre:
            continue
        jugadores.setdefault(nombre, []).append(r)

    resultados = []
    for nombre, partidas in jugadores.items():
        valor = calcular_valor(partidas, metrica.value)
        if valor is not None:
            resultados.append((nombre, valor))

    if not resultados:
        await interaction.followup.send("No hay suficientes datos todavía para calcular ese ranking.")
        return

    resultados.sort(key=lambda x: x[1], reverse=True)
    top10 = resultados[:10]

    medallas = ["🥇", "🥈", "🥉"]
    lineas = []
    for i, (nombre, valor) in enumerate(top10):
        prefijo = medallas[i] if i < 3 else f"{i+1}."
        lineas.append(f"{prefijo} **{nombre}** — {valor:,.2f}")

    alcance = f"Jornada: {jornada}" if jornada else "Acumulado de toda la liga"
    embed = discord.Embed(
        title=f"🏆 Ranking: {metrica.name}",
        description="\n".join(lineas),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=alcance)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="jornadas", description="Lista todas las jornadas/torneos registrados en la liga")
async def jornadas(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        rows = get_all_rows()
    except Exception as e:
        await interaction.followup.send(f"Error al leer la hoja: {e}")
        return

    lista = refresh_jornadas_cache(rows)
    if not lista:
        await interaction.followup.send("Todavía no hay ninguna jornada registrada.")
        return

    texto = "\n".join(f"• {j}" for j in lista)
    embed = discord.Embed(title="📅 Jornadas registradas", description=texto, color=discord.Color.blurple())
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="registrar", description="(Staff) Registra una partida en la hoja de estadísticas")
@app_commands.describe(
    jornada="Jornada/torneo al que pertenece esta partida (ej: 'Jornada 1', 'Torneo Apertura J3')",
    juego="Nombre del juego (ej: League of Legends, Dota 2, Smite)",
    jugador="Nombre del jugador",
    equipo="Equipo del jugador",
    resultado="Victoria o Derrota",
    dano="Daño hecho en la partida",
    kills="Kills en la partida",
    muertes="Muertes en la partida",
    asistencias="Asistencias en la partida",
)
@app_commands.choices(resultado=[
    app_commands.Choice(name="Victoria", value="Victoria"),
    app_commands.Choice(name="Derrota", value="Derrota"),
])
@app_commands.autocomplete(jornada=jornada_autocomplete)
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
):
    if not is_staff(interaction):
        await interaction.response.send_message(
            "Solo el staff puede registrar partidas.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        sheet = get_sheet()
        fecha = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        sheet.append_row([
            fecha, jornada, juego, jugador, equipo, resultado.value,
            dano, kills, muertes, asistencias,
        ])
        await interaction.followup.send(
            f"✅ Partida registrada: **{jugador}** ({equipo}) — {jornada}, {resultado.value}, "
            f"daño {dano:,.0f}, KDA {kills}/{muertes}/{asistencias}."
        )
    except Exception as e:
        await interaction.followup.send(f"Error al guardar en la hoja: {e}")


if __name__ == "__main__":
    if not DISCORD_TOKEN or not SHEET_ID:
        raise SystemExit(
            "Faltan variables de entorno. Revisa DISCORD_TOKEN y SHEET_ID en tu archivo .env"
        )
    bot.run(DISCORD_TOKEN)
