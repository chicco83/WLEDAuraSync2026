# ==============================================================================
# main.py
# Versioning:
#   v1.1 - 2026-09-07 - Protocollo seriale WLED aggiornato al firmware stock.
#          Il firmware WLED custom del fork ShadyNawara/WLED (menzionato nel
#          README) non serve piu': dal PR ufficiale #2156 "Added JSON API
#          over serial support" (2021), qualsiasi build recente di WLED
#          risponde al comando 'l' con un array JSON di interi decimali
#          "[16711680,65280,...]" (un colore per pixel, formato
#          0xWWRRGGBB), non piu' con l'oggetto {"leds":["RRGGBB",...]} del
#          vecchio firmware custom. Aggiornato il parsing per il nuovo
#          formato (vedi sezioni commentate "v1.0").
#   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
# ==============================================================================
import win32com.client
import serial
import json
import sys


###########
## User Configurable Section or through command line
###########
wled_com_port = "COM3"
wled_baud_rate = 115200

if len(sys.argv) > 1:
    wled_com_port = str(sys.argv[1])
    if len(sys.argv) > 2:
        wled_baud_rate = int(sys.argv[2])
#
## End of User Configurable Section
###########


wled_serial = serial.Serial(port=wled_com_port, baudrate=wled_baud_rate)

auraSdk = win32com.client.Dispatch("aura.sdk.1")
auraSdk.SwitchMode()
devices = auraSdk.Enumerate(0)

while True:
    wled_serial.write(b'l')
    led_values = json.loads(wled_serial.readline())

    # --- v1.0 (originale, formato firmware custom {"leds": ["RRGGBB", ...]}) ---
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
    # v1.1 (2026-09-07): con il firmware WLED stock la risposta al comando 'l'
    # e' gia' l'array dei colori dei pixel (interi, formato 0xWWRRGGBB di
    # NeoPixelBus), non un oggetto con chiave "leds" fatto di stringhe
    # esadecimali "RRGGBB". Estraiamo R,G,B dall'intero (il canale W viene
    # ignorato, l'SDK Aura qui non lo gestisce) e li ricomponiamo nel formato
    # 0x00BBGGRR atteso dall'SDK Aura.
    if isinstance(led_values, list):
        led_index = 0
        led_response_count = len(led_values)
        for dev in devices:
            for i in range(dev.Lights.Count):
                if led_index >= led_response_count:
                    break
                packed_color = led_values[led_index]
                r = (packed_color >> 16) & 0xFF
                g = (packed_color >> 8) & 0xFF
                b = packed_color & 0xFF
                dev.Lights(i).Color = (b << 16) | (g << 8) | r
                led_index += 1
            dev.Apply()
