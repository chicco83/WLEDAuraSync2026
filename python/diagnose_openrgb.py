# ==============================================================================
# diagnose_openrgb.py
# Versioning:
#   v1.0 - 2026-09-07 - Prima versione.
#          Script diagnostico standalone (non fa parte dell'app principale)
#          per capire esattamente in quale punto dell'handshake del
#          protocollo SDK di OpenRGB il server chiude la connessione. Parla
#          il protocollo direttamente via socket, senza passare dalla
#          libreria openrgb-python, cosi' isoliamo se il problema e'
#          nella libreria o nel server stesso. Usato per diagnosticare un
#          OpenRGBDisconnected senza messaggio con una build sperimentale di
#          OpenRGB (SDK Version 6) su un ROG STRIX B650-A GAMING WIFI: la
#          libreria Python risultava incolpevole (bug diverso gia' corretto
#          a monte, vedi requirements.txt), il sospetto e' un problema lato
#          server quando si richiedono i dati di un controller specifico.
#
# Uso: python diagnose_openrgb.py [host] [porta]
#      (default: 127.0.0.1 6742, gli stessi di OpenRGB)
# ==============================================================================
import socket
import struct
import sys
import time

MAGIC = b"ORGB"
HEADER_SIZE = 16

PKT_REQUEST_CONTROLLER_COUNT = 0
PKT_REQUEST_CONTROLLER_DATA = 1
PKT_REQUEST_PROTOCOL_VERSION = 40
PKT_SET_CLIENT_NAME = 50

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 6742

sys.stdout.reconfigure(line_buffering=True)


def send_packet(sock, dev_id, pkt_id, data=b""):
    header = MAGIC + struct.pack("<III", dev_id, pkt_id, len(data))
    sock.sendall(header + data)


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(
                "il server ha chiuso la connessione mentre leggevo %d byte (ricevuti solo %d)" % (n, len(buf))
            )
        buf += chunk
    return buf


def recv_packet(sock, timeout):
    sock.settimeout(timeout)
    header = recv_exact(sock, HEADER_SIZE)
    magic = header[0:4]
    dev_id, pkt_id, size = struct.unpack("<III", header[4:16])
    if magic != MAGIC:
        raise ValueError("firma pacchetto non valida: %r (mi aspettavo %r)" % (magic, MAGIC))
    data = recv_exact(sock, size) if size else b""
    return dev_id, pkt_id, data


print("Connessione TCP a %s:%d..." % (host, port))
sock = socket.create_connection((host, port), timeout=3)
print("OK, connesso via TCP.")

print("Passo 1: invio REQUEST_PROTOCOL_VERSION (versione richiesta dal client: 4)...")
send_packet(sock, 0, PKT_REQUEST_PROTOCOL_VERSION, struct.pack("<I", 4))
try:
    dev_id, pkt_id, data = recv_packet(sock, timeout=2)
    server_version = struct.unpack("<I", data)[0] if len(data) == 4 else None
    print("  -> risposta ricevuta, versione protocollo del server: %s" % server_version)
except socket.timeout:
    print("  -> nessuna risposta entro 2s (puo' essere normale se il server e' in modalita' protocollo 0)")
except Exception as e:
    print("  -> ERRORE: %r" % e)
    sys.exit(1)

print("Passo 2: invio SET_CLIENT_NAME...")
send_packet(sock, 0, PKT_SET_CLIENT_NAME, b"DiagnosticaOpenRGB\x00")
print("  -> nome inviato (questo pacchetto non ha risposta, aspetto un attimo per vedere se il server chiude)")
time.sleep(0.5)

print("Passo 3: invio REQUEST_CONTROLLER_COUNT...")
send_packet(sock, 0, PKT_REQUEST_CONTROLLER_COUNT)
try:
    dev_id, pkt_id, data = recv_packet(sock, timeout=3)
    count = struct.unpack("<I", data)[0] if len(data) == 4 else None
    print("  -> risposta ricevuta, numero di controller: %s" % count)
except Exception as e:
    print("  -> ERRORE: %r" % e)
    sys.exit(1)

for i in range(count):
    print("Passo 4.%d: richiedo REQUEST_CONTROLLER_DATA per il controller %d..." % (i, i))
    send_packet(sock, i, PKT_REQUEST_CONTROLLER_DATA)
    try:
        dev_id, pkt_id, data = recv_packet(sock, timeout=3)
        print("  -> controller %d: ricevuti %d byte di dati, tutto ok" % (i, len(data)))
    except Exception as e:
        print("  -> ERRORE sul controller %d: %r" % (i, e))
        sys.exit(1)

print("Tutti i %d controller letti correttamente: nessun blocco rilevato a questo livello di protocollo." % count)
