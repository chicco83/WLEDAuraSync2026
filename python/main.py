# ==============================================================================
# main.py
# Versioning:
#   v1.4 - 2026-09-07 - Aggiunti messaggi di stato a console.
#          Lo script non ha mai stampato nulla (nemmeno nella versione
#          originale del 2021): un funzionamento corretto e un blocco reale
#          erano quindi indistinguibili a schermo. Aggiunti messaggi di
#          connessione, elenco dispositivi Aura trovati e un contatore fps
#          ogni secondo, sul modello di SHOW_INFO/SHOW_FPS della versione
#          C++. Se lo script sembra "bloccato" ma non stampa nemmeno "In
#          attesa del primo frame live da WLED...", il problema e' prima
#          del loop principale (connessione WebSocket o Aura SDK).
#   v1.3 - 2026-09-07 - Corretto formato dati del WebSocket live view.
#          Il commento della v1.2 assumeva che {"lv":true} sul WebSocket
#          restituisse lo stesso JSON {"leds":[...]} dell'endpoint HTTP
#          /json/live: sbagliato. Verificato nel sorgente ufficiale di WLED
#          (wled00/data/liveview.htm, il codice usato dall'anteprima live
#          nell'interfaccia web) che il WebSocket manda invece un frame
#          BINARIO per ogni update:
#            - byte 0: 'L' (76) - firma del pacchetto, altrimenti da scartare
#            - byte 1: 2 se e' una matrice 2D (header di 4 byte totali),
#              qualsiasi altro valore per una striscia 1D (header di 2 byte)
#            - a seguire: 3 byte per pixel, in ordine R, G, B (niente stringhe
#              esadecimali, niente virgolette JSON)
#          L'endpoint HTTP /json/live (usato dalla versione C++) invece
#          restituisce davvero JSON: non serve cambiare nulla li'.
#   v1.2 - 2026-09-07 - Passaggio da seriale USB a WiFi (WebSocket). Formato
#          dati assunto erroneamente (vedi v1.3).
#   v1.1 - 2026-09-07 - Protocollo seriale WLED aggiornato al firmware stock.
#   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
# ==============================================================================
import win32com.client
import websocket
import sys
import time


###########
## User Configurable Section or through command line
###########
wled_host = "wled.local"  # hostname mDNS o IP del dispositivo WLED

if len(sys.argv) > 1:
    wled_host = str(sys.argv[1])
#
## End of User Configurable Section
###########


# --- v1.0/v1.1 (originali, comunicazione via porta seriale USB) -------------
# wled_com_port = "COM3"
# wled_baud_rate = 115200
# if len(sys.argv) > 1:
#     wled_com_port = str(sys.argv[1])
#     if len(sys.argv) > 2:
#         wled_baud_rate = int(sys.argv[2])
# wled_serial = serial.Serial(port=wled_com_port, baudrate=wled_baud_rate)
# -----------------------------------------------------------------------------
# v1.2/v1.3 (2026-09-07): connessione WebSocket al posto della seriale. Con
# {"lv":true} chiediamo a WLED di iniziare lo streaming live dei pixel.
print("Connessione a WLED su " + wled_host + " (WebSocket)...")
wled_ws_url = "ws://" + wled_host + "/ws"
wled_ws = websocket.create_connection(wled_ws_url, timeout=5)
wled_ws.send('{"lv":true}')
print("Connesso. In attesa del primo frame live da WLED...")

auraSdk = win32com.client.Dispatch("aura.sdk.1")
auraSdk.SwitchMode()
devices = auraSdk.Enumerate(0)

# v1.4: elenco dispositivi Aura trovati, utile per capire se il servizio
# Aura Sync/Armoury Crate e' raggiungibile e quante luci vede davvero.
print("Trovati " + str(devices.Count) + " dispositivi Aura Sync:")
for dev in devices:
    print(" - " + dev.Name + " : " + str(dev.Lights.Count) + " led")

frame_count = 0
t_start = time.time()

while True:
    # --- v1.0/v1.1 (originali, richiesta/risposta via seriale) -------------
    # wled_serial.write(b'l')
    # led_values = json.loads(wled_serial.readline())
    # --- v1.2 (WebSocket, formato JSON assunto per errore) ------------------
    # led_values = json.loads(wled_ws.recv())
    # if "leds" in led_values:
    #     led_index = 0
    #     led_response_count = len(led_values["leds"])
    #     for dev in devices:
    #         for i in range(dev.Lights.Count):
    #             if led_index >= led_response_count:
    #                 break
    #             rgb = led_values["leds"][led_index]
    #             dev.Lights(i).Color = int("0x00"+rgb[-2:] + rgb[2:-2] + rgb[0:2], 16)
    #             led_index += 1
    #         dev.Apply()
    # -----------------------------------------------------------------------------
    # v1.3 (2026-09-07): il WebSocket manda un frame binario (vedi versioning
    # sopra), non JSON. websocket-client ritorna bytes per i frame binari.
    frame = wled_ws.recv()

    if not isinstance(frame, (bytes, bytearray)) or len(frame) < 3 or frame[0] != 76:  # 76 = 'L'
        continue  # es. il primo messaggio dopo la connessione e' testo/JSON di stato, non live view

    header_len = 4 if frame[1] == 2 else 2  # 2D (matrice) vs 1D (striscia)
    pixels = frame[header_len:]
    led_response_count = len(pixels) // 3  # 3 byte (R, G, B) per pixel

    led_index = 0
    for dev in devices:
        for i in range(dev.Lights.Count):
            if led_index >= led_response_count:
                break
            offset = led_index * 3
            r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]
            dev.Lights(i).Color = (b << 16) | (g << 8) | r  # Aura sdk expects 0x00BBGGRR
            led_index += 1
        dev.Apply()

    # v1.4: contatore fps a console ogni secondo, per vedere a colpo d'occhio
    # che il loop sta ricevendo ed applicando dati reali.
    frame_count += 1
    now = time.time()
    if now - t_start >= 1.0:
        print(str(frame_count) + " fps, " + str(led_response_count) + " led")
        frame_count = 0
        t_start = now
