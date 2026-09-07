# ==============================================================================
# main.py
# Versioning:
#   v1.2 - 2026-09-07 - Passaggio da seriale USB a WiFi (WebSocket).
#          Alcune schede (es. D1 mini incollato dentro una lampada con solo
#          il cavo USB originale, senza i fili dati) non espongono una porta
#          seriale utilizzabile dal PC. WLED pero' espone via rete la stessa
#          "live view" usata dall'anteprima nell'interfaccia web: connesso
#          al WebSocket ws://<host>/ws, mandando una volta {"lv":true},
#          WLED comincia a inviare in streaming un JSON per frame nello
#          stesso formato {"leds": ["RRGGBB", ...]} gia' gestito qui sotto
#          (non serve piu' nessun firmware custom, ne' la seriale). Il primo
#          argomento non e' piu' la porta COM ma l'hostname mDNS (es.
#          "wled-lampada.local") o l'IP del dispositivo WLED.
#          NB: la risoluzione di hostname ".local" su Windows richiede il
#          supporto mDNS del sistema (es. servizio Bonjour installato da
#          iTunes/altro software Apple, o il supporto nativo se presente);
#          se "wled-lampada.local" non viene risolto, usa direttamente
#          l'IP del dispositivo (lo trovi nell'app WLED o nel router).
#   v1.1 - 2026-09-07 - Protocollo seriale WLED aggiornato al firmware stock
#          (vedi sezioni commentate sotto). Superato dal passaggio a WiFi.
#   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
# ==============================================================================
import win32com.client
import websocket
import json
import sys


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
# v1.2 (2026-09-07): connessione WebSocket al posto della seriale. Con
# {"lv":true} chiediamo a WLED di iniziare lo streaming live dei pixel.
wled_ws_url = "ws://" + wled_host + "/ws"
wled_ws = websocket.create_connection(wled_ws_url, timeout=5)
wled_ws.send('{"lv":true}')

auraSdk = win32com.client.Dispatch("aura.sdk.1")
auraSdk.SwitchMode()
devices = auraSdk.Enumerate(0)

while True:
    # --- v1.0/v1.1 (originali, richiesta/risposta via seriale) -------------
    # wled_serial.write(b'l')
    # led_values = json.loads(wled_serial.readline())
    # -------------------------------------------------------------------------
    # v1.2 (2026-09-07): il WebSocket invia i frame in streaming, non serve
    # piu' richiederli uno a uno: basta leggere il prossimo messaggio.
    led_values = json.loads(wled_ws.recv())

    if "leds" in led_values:
        led_index = 0
        led_response_count = len(led_values["leds"])
        for dev in devices:
            for i in range(dev.Lights.Count):
                if led_index >= led_response_count:
                    break
                rgb = led_values["leds"][led_index]
                dev.Lights(i).Color = int("0x00"+rgb[-2:] + rgb[2:-2] + rgb[0:2], 16)
                led_index += 1
            dev.Apply()
