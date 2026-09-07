# ==============================================================================
# main.py
# Versioning:
#   v1.6 - 2026-09-07 - Fix "Trovati 0 dispositivi Aura Sync".
#          WLED ora funziona (confermato: dati live ricevuti correttamente,
#          fps stabili). Il problema restante era lato Aura: Enumerate()
#          chiamato subito dopo SwitchMode() tornava una collezione vuota.
#          Aggiunta una breve attesa tra le due chiamate (il servizio Aura
#          Sync/Armoury Crate impiega un istante a passare in modalita'
#          controllo SDK) e un messaggio diagnostico se restano comunque 0
#          dispositivi (servizio non attivo, permessi, Aura Sync disattivato
#          in Armoury Crate).
#   v1.5 - 2026-09-07 - Fix output bufferizzato + timeout/diagnostica sul
#          WebSocket.
#          1) print() non appariva a schermo (PowerShell) perche' Python
#             bufferizza lo stdout quando non riconosce bene il terminale:
#             il traceback di un KeyboardInterrupt manuale ha mostrato che lo
#             script era in realta' gia' dentro il loop principale, oltre
#             tutte le stampe di stato. Forzato l'unbuffering dello stdout.
#          2) Il vero problema e' che wled_ws.recv() restava bloccato per
#             sempre: nessun frame live arrivava da WLED. Il timeout passato
#             a create_connection() non si applicava alle recv() successive
#             alla connessione iniziale; ora viene impostato esplicitamente
#             con wled_ws.settimeout(). Se scatta il timeout, ri-mandiamo
#             {"lv":true} (magari il flag si e' disattivato, es. un altro
#             client - tipo l'anteprima live nell'interfaccia web di WLED -
#             ha preso il turno) e stampiamo ogni messaggio non riconosciuto
#             (tipo/contenuto) cosi' si vede cosa manda davvero WLED invece
#             di scartarlo in silenzio.
#   v1.4 - 2026-09-07 - Aggiunti messaggi di stato a console (connessione,
#          dispositivi Aura trovati, contatore fps).
#   v1.3 - 2026-09-07 - Corretto formato dati del WebSocket live view: frame
#          BINARIO ('L' + flag dimensione + terne RGB), non JSON come
#          assunto nella v1.2. L'endpoint HTTP /json/live (versione C++)
#          restituisce invece davvero JSON, li' non cambia nulla.
#   v1.2 - 2026-09-07 - Passaggio da seriale USB a WiFi (WebSocket).
#   v1.1 - 2026-09-07 - Protocollo seriale WLED aggiornato al firmware stock.
#   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
# ==============================================================================
import win32com.client
import websocket
import sys
import time

# v1.5: forza l'output a video subito, invece di restare nel buffer di
# Python finche' il processo non termina o il buffer non si riempie.
sys.stdout.reconfigure(line_buffering=True)


###########
## User Configurable Section or through command line
###########
wled_host = "wled.local"  # hostname mDNS o IP del dispositivo WLED
RECV_TIMEOUT_SECONDS = 3  # se non arriva nessun frame entro questo tempo, ri-chiediamo la live view

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
wled_ws.settimeout(RECV_TIMEOUT_SECONDS)  # v1.5: garantisce il timeout anche sulle recv() successive
wled_ws.send('{"lv":true}')
print("Connesso. In attesa del primo frame live da WLED...")

auraSdk = win32com.client.Dispatch("aura.sdk.1")
auraSdk.SwitchMode()
# v1.6 (2026-09-07): Enumerate() chiamato subito dopo SwitchMode() puo'
# tornare una collezione vuota perche' il servizio Aura Sync/Armoury Crate
# impiega un istante a passare in modalita' controllo SDK. Piccola attesa
# per dargli il tempo di popolare l'elenco dispositivi.
time.sleep(1)
devices = auraSdk.Enumerate(0)

# v1.4: elenco dispositivi Aura trovati, utile per capire se il servizio
# Aura Sync/Armoury Crate e' raggiungibile e quante luci vede davvero.
print("Trovati " + str(devices.Count) + " dispositivi Aura Sync:")
if devices.Count == 0:
    print("Nessun dispositivo trovato. Verifica che: Armoury Crate/Aura Sync sia aperto,")
    print("che lo script sia eseguito come Amministratore, e che 'Aura Sync' sia attivo")
    print("(interruttore generale + per singolo dispositivo) nelle impostazioni di Armoury Crate.")
for dev in devices:
    print(" - " + dev.Name + " : " + str(dev.Lights.Count) + " led")

frame_count = 0
t_start = time.time()
unexpected_messages_logged = 0  # v1.5: limita quanti messaggi "strani" stampiamo, per non intasare la console

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
    # v1.5: try/except per non restare bloccati in eterno se WLED smette di
    # mandare la live view.
    try:
        frame = wled_ws.recv()
    except (websocket.WebSocketTimeoutException, TimeoutError):
        print("Nessun frame ricevuto da " + str(RECV_TIMEOUT_SECONDS) + "s, richiedo di nuovo la live view...")
        wled_ws.send('{"lv":true}')
        continue

    if not isinstance(frame, (bytes, bytearray)) or len(frame) < 3 or frame[0] != 76:  # 76 = 'L'
        # v1.5: stampiamo cosa arriva davvero (limitato alle prime volte) invece
        # di scartarlo in silenzio - aiuta a capire se WLED risponde con un
        # errore testuale invece della live view binaria attesa.
        if unexpected_messages_logged < 5:
            preview = frame if isinstance(frame, str) else repr(frame[:32])
            print("Messaggio inatteso (non e' un frame live view): " + str(preview))
            unexpected_messages_logged += 1
        continue

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
