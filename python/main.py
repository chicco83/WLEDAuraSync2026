# ==============================================================================
# main.py
# Versioning:
#   v2.4 - 2026-09-07 - Diagnostica sulla modalita' dei dispositivi OpenRGB.
#          Connessione, WLED e fps tutti confermati funzionanti, ma le luci
#          non seguivano i colori: possibile causa e' che il dispositivo non
#          abbia una modalita' chiamata "Direct" (necessaria perche'
#          set_colors() abbia effetto), es. perche' il driver sperimentale
#          del nuovo controller usa un altro nome o non la implementa ancora.
#          Ora si stampano modalita' attuale, elenco delle disponibili, ed
#          esito del cambio a "Direct" per ogni dispositivo, invece di
#          ignorare l'errore in silenzio.
#   v2.3 - 2026-09-07 - Forzata protocol_version=0 nella connessione a
#          OpenRGBClient. Uno script diagnostico standalone (diagnose_openrgb.py)
#          che parla il protocollo via socket grezzo ha dimostrato che
#          l'handshake e la lettura dei dati di tutti i controller funzionano
#          perfettamente anche con il server sperimentale (SDK v6): quindi
#          OpenRGBDisconnected non viene dal server che chiude la connessione,
#          ma da openrgb-python che si disconnette da solo perche' non
#          interpreta correttamente qualche campo del formato dati dei
#          controller a protocollo >= 1 (oltre al bug gia' corretto in v2.2).
#          Forzando protocol_version=0 chiediamo al server il formato dati
#          piu' semplice/vecchio possibile, che la libreria sa sicuramente
#          gestire.
#   v2.2 - 2026-09-07 - Causa esatta trovata per il blocco su OpenRGB "SDK
#          Version 6" (build sperimentale): bug noto di openrgb-python
#          <=0.3.6 (desync nel parsing delle zone con server a protocollo
#          SDK >= 5, vedi requirements.txt), corretto su GitHub ma non
#          ancora rilasciato su PyPI. Nessuna modifica di codice qui: basta
#          installare openrgb-python dal commit con il fix (vedi
#          requirements.txt) invece che dalla release PyPI.
#   v2.1 - 2026-09-07 - Diagnostica migliorata sulla connessione a OpenRGB.
#          La porta 6742 puo' risultare raggiungibile (test TCP riuscito) ma
#          la connessione OpenRGBClient() fallire comunque, con un'eccezione
#          senza messaggio (es. TimeoutError vuoto durante l'handshake del
#          protocollo SDK - capita con build di sviluppo/nightly di OpenRGB
#          che possono usare un protocollo diverso da quello supportato da
#          openrgb-python). Ora si stampa tipo ed eventuale messaggio
#          dell'eccezione invece del solo str(e), spesso vuoto.
#   v2.0 - 2026-09-07 - Sostituito l'SDK Aura con OpenRGB.
#          Confermato su hardware reale: su schede AM5 con header ARGB "Gen 2"
#          (es. ROG STRIX B650-A GAMING WIFI) il controller e' gestito via USB
#          ("Aura USB Controller") e Armoury Crate lo pilota correttamente,
#          ma la libreria COM legacy AuraServiceLib/aura.sdk.1 (SDK Aura V3.1,
#          2019-2020) non e' mai stata aggiornata per riconoscerlo:
#          Enumerate() tornava sempre 0 dispositivi, sia con Armoury Crate che
#          con Aura Creator, nonostante il servizio LightingService fosse
#          regolarmente in esecuzione. OpenRGB invece ha un driver dedicato
#          per questo controller e lo rileva. Da qui in poi il progetto
#          controlla le luci tramite il server SDK di OpenRGB (libreria
#          "openrgb-python") invece che tramite win32com/AuraServiceLib.
#          Richiede: OpenRGB in esecuzione con "SDK Server" attivo
#          (Settings > SDK Server > Server Enabled, porta di default 6742) e
#          Armoury Crate chiuso (LightingService fermo) altrimenti si
#          contendono l'accesso hardware.
#   v1.6 - 2026-09-07 - Fix "Trovati 0 dispositivi Aura Sync" (attesa dopo
#          SwitchMode). Non ha risolto: causa reale scoperta poi in v2.0.
#   v1.5 - 2026-09-07 - Fix output bufferizzato + timeout/diagnostica sul
#          WebSocket (stdout non appariva, wled_ws.recv() restava bloccato).
#   v1.4 - 2026-09-07 - Aggiunti messaggi di stato a console.
#   v1.3 - 2026-09-07 - Corretto formato dati del WebSocket live view: frame
#          BINARIO ('L' + flag dimensione + terne RGB), non JSON.
#   v1.2 - 2026-09-07 - Passaggio da seriale USB a WiFi (WebSocket).
#   v1.1 - 2026-09-07 - Protocollo seriale WLED aggiornato al firmware stock.
#   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
# ==============================================================================
import websocket
import sys
import time
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

# v1.5: forza l'output a video subito, invece di restare nel buffer di
# Python finche' il processo non termina o il buffer non si riempie.
sys.stdout.reconfigure(line_buffering=True)


###########
## User Configurable Section or through command line
###########
wled_host = "wled.local"  # hostname mDNS o IP del dispositivo WLED
openrgb_host = "127.0.0.1"  # OpenRGB gira sullo stesso PC di questo script, di norma
openrgb_port = 6742  # porta di default del "SDK Server" di OpenRGB
RECV_TIMEOUT_SECONDS = 3  # se non arriva nessun frame entro questo tempo, ri-chiediamo la live view

if len(sys.argv) > 1:
    wled_host = str(sys.argv[1])
    if len(sys.argv) > 2:
        openrgb_host = str(sys.argv[2])
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

# --- v1.0-v1.6 (originali/precedenti, controllo luci via SDK Aura) ----------
# auraSdk = win32com.client.Dispatch("aura.sdk.1")
# auraSdk.SwitchMode()
# time.sleep(1)  # v1.6: dava tempo al servizio Aura di popolare l'elenco
# devices = auraSdk.Enumerate(0)
# print("Trovati " + str(devices.Count) + " dispositivi Aura Sync:")
# if devices.Count == 0:
#     print("Nessun dispositivo trovato. Verifica che: Armoury Crate/Aura Sync sia aperto,")
#     print("che lo script sia eseguito come Amministratore, e che 'Aura Sync' sia attivo")
#     print("(interruttore generale + per singolo dispositivo) nelle impostazioni di Armoury Crate.")
# for dev in devices:
#     print(" - " + dev.Name + " : " + str(dev.Lights.Count) + " led")
# -----------------------------------------------------------------------------
# v2.0 (2026-09-07): connessione al server SDK di OpenRGB al posto dell'SDK
# Aura. OpenRGB deve essere gia' avviato con "SDK Server" attivo.
# v2.3 (2026-09-07): uno script diagnostico a basso livello (senza passare da
# questa libreria) ha confermato che l'handshake e i dati dei controller
# arrivano correttamente anche da una build sperimentale con protocollo SDK
# v6: il problema e' quindi nel parsing di openrgb-python, non nel server.
# Forziamo la richiesta della versione di protocollo piu' bassa/semplice (0)
# invece del default della libreria (4), cosi' il server serializza i dati
# nel formato piu' elementare possibile, aggirando eventuali campi aggiunti
# nei protocolli v4/v5/v6 che la libreria non gestisce ancora correttamente.
print("Connessione a OpenRGB su " + openrgb_host + ":" + str(openrgb_port) + "...")
try:
    orgb_client = OpenRGBClient(address=openrgb_host, port=openrgb_port, name="WLEDAuraSync", protocol_version=0)
except Exception as e:
    # v2.1 (2026-09-07): la porta puo' essere raggiungibile (TCP connesso) ma
    # l'handshake del protocollo SDK fallire lo stesso, es. per un
    # disallineamento di versione tra questa libreria (openrgb-python) e una
    # build di sviluppo di OpenRGB che parla un protocollo piu' recente. In
    # quel caso l'eccezione originale (spesso senza messaggio) non bastava a
    # capire cosa fosse successo: stampiamo tipo ed eventuale messaggio.
    print("Impossibile connettersi a OpenRGB: " + type(e).__name__ + (": " + str(e) if str(e) else " (nessun messaggio)"))
    print("Verifica che OpenRGB sia avviato con il server SDK attivo. Se stai usando una build di")
    print("sviluppo/nightly, prova la versione stabile: potrebbe usare un protocollo SDK piu' recente")
    print("di quello supportato da questa libreria (openrgb-python).")
    sys.exit(1)

devices = orgb_client.devices
print("Trovati " + str(len(devices)) + " dispositivi OpenRGB:")
if len(devices) == 0:
    print("Nessun dispositivo trovato da OpenRGB. Apri OpenRGB e premi 'Detect Devices',")
    print("e verifica che Armoury Crate sia chiuso (LightingService fermo): i due si contendono")
    print("l'accesso hardware, se Armoury Crate lo tiene occupato OpenRGB non vede nulla.")
for dev in devices:
    print(" - " + dev.name + " : " + str(len(dev.leds)) + " led")
    # v2.4 (2026-09-07): i dati arrivavano da WLED e la connessione a OpenRGB
    # funzionava, ma le luci non si muovevano: sospetto e' che il dispositivo
    # non abbia una modalita' chiamata esattamente "Direct" (il driver
    # sperimentale di un controller nuovo potrebbe usare un altro nome, o
    # nessuna modalita' di controllo diretto). Ora stampiamo la modalita'
    # attuale, l'elenco di quelle disponibili, e se il cambio a "Direct" e'
    # riuscito o no, invece di ignorare l'errore in silenzio.
    mode_names = [m.name for m in dev.modes]
    current_mode_name = dev.modes[dev.active_mode].name if dev.active_mode is not None and dev.active_mode >= 0 else "?"
    print("   modalita' attuale: " + current_mode_name + " | disponibili: " + str(mode_names))
    try:
        dev.set_mode("Direct")
        print("   modalita' impostata su 'Direct' con successo")
    except ValueError:
        print("   ATTENZIONE: nessuna modalita' chiamata 'Direct' su questo dispositivo -")
        print("   set_colors() probabilmente non avra' alcun effetto visibile (vedi elenco sopra)")

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

    # --- v1.0-v1.6 (originali/precedenti, un colore alla volta via SDK Aura) --
    # led_index = 0
    # for dev in devices:
    #     for i in range(dev.Lights.Count):
    #         if led_index >= led_response_count:
    #             break
    #         offset = led_index * 3
    #         r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]
    #         dev.Lights(i).Color = (b << 16) | (g << 8) | r  # Aura sdk expects 0x00BBGGRR
    #         led_index += 1
    #     dev.Apply()
    # -----------------------------------------------------------------------------
    # v2.0 (2026-09-07): OpenRGB si aggiorna un dispositivo alla volta con
    # set_colors(), che pero' richiede sempre una lista lunga esattamente
    # quanto i led del dispositivo (a differenza dell'SDK Aura, non si puo'
    # aggiornarne solo una parte): i led oltre i dati ricevuti da WLED
    # vengono spenti (nero) invece di lasciarli con il colore precedente.
    led_index = 0
    for dev in devices:
        colors = []
        for i in range(len(dev.leds)):
            if led_index < led_response_count:
                offset = led_index * 3
                colors.append(RGBColor(pixels[offset], pixels[offset + 1], pixels[offset + 2]))
                led_index += 1
            else:
                colors.append(RGBColor(0, 0, 0))
        dev.set_colors(colors, fast=True)

    # v1.4: contatore fps a console ogni secondo, per vedere a colpo d'occhio
    # che il loop sta ricevendo ed applicando dati reali.
    frame_count += 1
    now = time.time()
    if now - t_start >= 1.0:
        print(str(frame_count) + " fps, " + str(led_response_count) + " led")
        frame_count = 0
        t_start = now
