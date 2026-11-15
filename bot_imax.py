import json
import os
import sys

import requests
from bs4 import BeautifulSoup

# ==========================================
# CONFIGURACIÓN
# ==========================================
# El token y el chat ID NO van acá: se leen de los "Secrets" de GitHub.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# Agregá acá las películas que querés monitorear (entre comillas, separadas por coma)
PELICULAS_BUSCADAS = ["Dune", "Doomsday"]

# Archivo donde se recuerdan las películas ya avisadas
ARCHIVO_ESTADO = "estado.json"

# Si es "1", el bot manda un mensaje de prueba aunque no haya películas buscadas
MODO_PRUEBA = os.environ.get("MODO_PRUEBA", "0") == "1"

URL = "https://entradas.todoshowcase.com/boleteria.aspx"


def cargar_estado():
  try:
    with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as f:
      return set(json.load(f).get("notificadas", []))
  except (FileNotFoundError, json.JSONDecodeError):
    return set()


def guardar_estado(notificadas):
  with open(ARCHIVO_ESTADO, "w", encoding="utf-8") as f:
    json.dump({"notificadas": sorted(notificadas)}, f, ensure_ascii=False, indent=2)


def enviar_telegram(mensaje):
  """Envía una notificación a Telegram. Devuelve True si salió bien."""
  if not TELEGRAM_TOKEN or not CHAT_ID:
    print("[!] Faltan TELEGRAM_TOKEN o CHAT_ID (revisá los Secrets de GitHub).")
    return False
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  data = {"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
  try:
    respuesta = requests.post(url, data=data, timeout=15)
    json_resp = respuesta.json()
    if json_resp.get("ok"):
      print("[+] Mensaje enviado a Telegram.")
      return True
    print(f"[!] Error de Telegram: {json_resp.get('description')}")
  except Exception as e:
    print(f"[!] Error de conexión con Telegram: {e}")
  return False


def obtener_peliculas_imax():
  """Consulta Showcase simulando la selección de IMAX Norcenter (ID 18).
  Devuelve una lista de títulos, o None si hubo un error."""
  session = requests.Session()
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  try:
    # 1. GET inicial para obtener los tokens de sesión de ASP.NET
    response_get = session.get(URL, headers=headers, timeout=20)
    print(f"[i] GET inicial: código {response_get.status_code}")
    if response_get.status_code != 200:
      print("[!] Showcase no respondió bien (¿bloqueo de IP?).")
      return None

    soup_get = BeautifulSoup(response_get.text, "html.parser")
    viewstate = soup_get.find("input", {"id": "__VIEWSTATE"})["value"]
    viewstategenerator = soup_get.find("input", {"id": "__VIEWSTATEGENERATOR"})["value"]
    eventvalidation = soup_get.find("input", {"id": "__EVENTVALIDATION"})["value"]

    # 2. Datos del formulario para seleccionar IMAX Norcenter (ID 18)
    payload = {
        "__EVENTTARGET": "ctl00$Contenido$lstCinemaFull",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": viewstategenerator,
        "__EVENTVALIDATION": eventvalidation,
        "ctl00$Contenido$lstCinemaFull": "18",
    }
    headers["X-MicrosoftAjax"] = "Delta=true"

    # 3. POST con la selección del cine
    response_post = session.post(URL, data=payload, headers=headers, timeout=20)
    print(f"[i] POST cine: código {response_post.status_code}")
    soup_post = BeautifulSoup(response_post.text, "html.parser")

    # 4. Extraer las películas del desplegable
    peliculas = []
    select_movies = soup_post.find("select", {"id": "ctl00_Contenido_lstMovies"})
    if select_movies:
      for option in select_movies.find_all("option"):
        titulo = option.text.strip()
        val = option.get("value", "")
        if val and "Seleccione" not in titulo:
          peliculas.append(titulo)
    return peliculas

  except Exception as e:
    print(f"[!] Error al consultar Showcase: {e}")
    return None


def main():
  notificadas = cargar_estado()
  peliculas = obtener_peliculas_imax()

  if peliculas is None:
    print("[!] No se pudo consultar la cartelera en esta ejecución.")
    if MODO_PRUEBA:
      enviar_telegram(
          "⚠️ <b>Prueba del bot:</b> Telegram funciona, pero no pude leer la"
          " cartelera de Showcase desde GitHub (posible bloqueo)."
      )
    sys.exit(0)

  print(f"[+] Películas en IMAX actualmente: {peliculas}")

  if MODO_PRUEBA:
    lista = "\n".join(f"• {p}" for p in peliculas) or "(lista vacía)"
    enviar_telegram(
        "✅ <b>Prueba del bot OK.</b> Cartelera IMAX leída correctamente:\n\n"
        + lista
    )

  cambios = False
  for peli_buscada in PELICULAS_BUSCADAS:
    for peli_cartelera in peliculas:
      if peli_buscada.lower() in peli_cartelera.lower():
        if peli_cartelera not in notificadas:
          mensaje = (
              "🚨 <b>¡ENTRADAS DISPONIBLES EN IMAX NORCENTER!</b> 🚨\n\n"
              f"La película <b>{peli_cartelera}</b> ya se encuentra disponible.\n\n"
              f"👉 Entrá ya a: {URL}"
          )
          if enviar_telegram(mensaje):
            notificadas.add(peli_cartelera)
            cambios = True

  if cambios:
    guardar_estado(notificadas)


if __name__ == "__main__":
  main()
