// ============================================================================
// WLEDAuraSync.cpp
// Versioning:
//   v1.4 - 2026-09-07 - Fix "Found 0 devices in Aura Sync" (verificato via
//          la versione Python: WLED/WiFi funzionano correttamente, il
//          problema era solo lato Aura). Enumerate() chiamato subito dopo
//          SwitchMode() puo' tornare una collezione vuota perche' il
//          servizio Aura Sync/Armoury Crate impiega un istante a passare in
//          modalita' controllo SDK. Aggiunta una breve attesa (Sleep) tra le
//          due chiamate e un messaggio diagnostico se restano comunque 0
//          dispositivi.
//   v1.3 - 2026-09-07 - Passaggio da seriale USB a WiFi (HTTP polling).
//          Alcune schede (es. D1 mini incollato dentro una lampada con solo
//          il cavo USB originale, senza i fili dati) non espongono una porta
//          seriale utilizzabile dal PC. WLED pero' espone via rete lo stesso
//          tipo di dati usato dall'anteprima "live view" dell'interfaccia
//          web, all'endpoint HTTP GET /json/live, nello stesso formato
//          {"leds": ["RRGGBB", ...]} gia' gestito da questo file prima
//          dell'introduzione (v1.2) del formato seriale stock (vedi sezioni
//          commentate sotto). Non serve piu' nessun firmware custom ne' la
//          seriale: la connessione usa WinHTTP (gia' incluso in Windows,
//          nessuna nuova libreria esterna). Il primo argomento non e' piu'
//          la porta COM ma l'hostname mDNS (es. "wled-lampada.local") o
//          l'IP del dispositivo WLED; il secondo argomento non e' piu' il
//          baud rate ma un intervallo minimo tra due richieste HTTP in
//          millisecondi (0 = nessuna attesa aggiuntiva).
//          NB: la libreria "serial" (wjwwood/serial) non e' piu' referenziata
//          da questo progetto: rimossa da WLEDAuraSync.vcxproj (i file restano
//          su disco per chi volesse tornare alla versione seriale).
//   v1.2 - 2026-09-07 - Protocollo seriale WLED aggiornato al formato stock
//          (array di interi invece di {"leds":[...]}"). Superato dal
//          passaggio a WiFi.
//   v1.1 - 2026-09-07 - Fix crash immediato all'avvio per eccezioni non
//          gestite sull'apertura della seriale e sull'SDK Aura.
//   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
// ============================================================================
#import "libid:F1AA5209-5217-4B82-BA7E-A68198999AFA"
#include <Windows.h>
#include <winhttp.h>
#include <comdef.h> // necessario per intercettare le eccezioni _com_error dell'SDK Aura
#include <iostream>
#include <string>
#include <vector>
#include <stdexcept>
#include "json/json.h"

#pragma comment(lib, "winhttp.lib")

//#define SHOW_FPS
#define SHOW_INFO

#ifdef SHOW_FPS
#include <chrono>
#include <ctime>
#endif


// v1.3: richiede /json/live a WLED via HTTP e ritorna il corpo della risposta.
// Lancia std::runtime_error se la richiesta fallisce (host irraggiungibile,
// WLED spento, rete assente, ecc). Chi chiama decide se ritentare.
static std::string fetchLiveLeds(HINTERNET hConnect)
{
	HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", L"/json/live", NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
	if (!hRequest) {
		throw std::runtime_error("WinHttpOpenRequest fallita");
	}

	std::string body;
	BOOL ok = WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
	if (ok) {
		ok = WinHttpReceiveResponse(hRequest, NULL);
	}
	if (ok) {
		DWORD available = 0;
		while (WinHttpQueryDataAvailable(hRequest, &available) && available > 0) {
			std::string chunk(available, '\0');
			DWORD bytesRead = 0;
			if (!WinHttpReadData(hRequest, &chunk[0], available, &bytesRead)) {
				break;
			}
			chunk.resize(bytesRead);
			body += chunk;
		}
	}
	WinHttpCloseHandle(hRequest);

	if (!ok) {
		throw std::runtime_error("richiesta HTTP a /json/live fallita (host irraggiungibile o WLED non risponde)");
	}
	return body;
}

int main(int argc, char** argv)
{
	//////////
	// User Configurable Section or through command line
	//////////
	std::string WLEDHOST = "wled.local"; // hostname mDNS o IP del dispositivo WLED
	int POLL_INTERVAL_MS = 0; // attesa minima tra due richieste HTTP, 0 = nessuna
	//
	//// End of User Configurable Section
	///////////

	// --- v1.0/v1.1/v1.2 (originali, porta COM + baud rate seriale) -------------
	// std::string WLEDCOMPORT = "COM5";
	// int WLEDBAUDRATE = 115200;
	// -----------------------------------------------------------------------------

	if (argc > 1) {
		WLEDHOST = std::string(argv[1]);
		if (argc > 2) {
			POLL_INTERVAL_MS = std::stoi(argv[2]);
		}
		if (argc > 3 && std::string(argv[3]) == "nowindow") {
			HWND consoleWindow = GetConsoleWindow(); // hide console window
			ShowWindow(consoleWindow, 0);
		}
	}

	std::wstring wideHost(WLEDHOST.begin(), WLEDHOST.end()); // WinHTTP vuole stringhe wide

	Json::CharReaderBuilder builder;
	const std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
	std::string json_string;

	JSONCPP_STRING json_err;
	Json::Value json_value;

	HRESULT hr;
	// Initialize COM
	hr = ::CoInitializeEx(nullptr, COINIT_MULTITHREADED);
	if (SUCCEEDED(hr))
	{
		// --- v1.0/v1.1 (originali, apertura porta seriale) --------------------
		// try {
		// 	wled_serial.open(); // open serial
		// }
		// catch (const std::exception& e) { ... }
		// if (wled_serial.isOpen()) { ... } else { return 1; }
		// -----------------------------------------------------------------------
		// v1.3 (2026-09-07): al posto della seriale, apriamo una sessione HTTP
		// verso l'host/IP di WLED con WinHTTP.
		HINTERNET hSession = WinHttpOpen(L"WLEDAuraSync/1.3", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
		HINTERNET hConnect = hSession ? WinHttpConnect(hSession, wideHost.c_str(), INTERNET_DEFAULT_HTTP_PORT, 0) : NULL;

		if (!hSession || !hConnect) {
			std::cerr << "Impossibile connettersi a " << WLEDHOST << " via HTTP." << std::endl;
			std::cerr << "Verifica che l'hostname/IP sia corretto e che il dispositivo WLED sia raggiungibile in rete (es. \"WLEDAuraSync.exe wled-lampada.local\")." << std::endl;
			if (hSession) WinHttpCloseHandle(hSession);
			::CoUninitialize();
			return 1;
		}

#ifdef SHOW_INFO
		std::cout << "Connesso a WLED su " << WLEDHOST << std::endl;
#endif

		// uninitialize on exit
		const int exit_callback = std::atexit([]() { ::CoUninitialize(); });

		// Create SDK instance
		AuraServiceLib::IAuraSdkPtr sdk = nullptr;
		hr = sdk.CreateInstance(__uuidof(AuraServiceLib::AuraSdk), nullptr, CLSCTX_INPROC_SERVER);
		if (SUCCEEDED(hr))
		{
			AuraServiceLib::IAuraSyncDeviceCollectionPtr devices;

			// v1.1/v1.3: IAuraSdkPtr e' uno smart pointer COM (_com_ptr_t) che
			// lancia _com_error se la chiamata fallisce (es. servizio Aura
			// Sync/Armoury Crate non in esecuzione). La SDK Aura usata resta
			// la V3.1 (tuttora l'ultima disponibile sul sito Asus).
			try {
				// Acquire control
				sdk->SwitchMode();
				// v1.4 (2026-09-07): Enumerate() chiamato subito dopo SwitchMode()
				// puo' tornare una collezione vuota perche' il servizio Aura
				// Sync/Armoury Crate impiega un istante a passare in modalita'
				// controllo SDK. Piccola attesa per dargli il tempo di popolare
				// l'elenco dispositivi.
				Sleep(1000);
				// Enumerate all devices
				devices = sdk->Enumerate(0); // 0 means ALL
			}
			catch (const _com_error& e) {
				std::cerr << "Errore comunicazione con Aura Sync SDK 3.1: " << (const char*)e.ErrorMessage() << " (HRESULT 0x" << std::hex << e.Error() << ")" << std::endl;
				std::cerr << "Verifica che il servizio Aura Sync / Armoury Crate sia installato e in esecuzione (Lighting Service attivo)." << std::endl;
				WinHttpCloseHandle(hConnect);
				WinHttpCloseHandle(hSession);
				return 1;
			}

			// v1.4: se non trova nessun dispositivo, il problema e' quasi
			// sempre il servizio Aura (non attivo, permessi, Aura Sync
			// disattivato in Armoury Crate), non questo programma.
			if (devices->Count == 0) {
				std::cerr << "Nessun dispositivo Aura Sync trovato." << std::endl;
				std::cerr << "Verifica che Armoury Crate/Aura Sync sia aperto, che l'exe sia eseguito come Amministratore," << std::endl;
				std::cerr << "e che \"Aura Sync\" sia attivo (interruttore generale + per singolo dispositivo) nelle impostazioni di Armoury Crate." << std::endl;
			}

#ifdef SHOW_INFO
			std::cout << "Found " + std::to_string(devices->Count) + " devices in Aura Sync" << std::endl;
			std::cout << std::endl;

			for (int i = 0; i < devices->Count; i++)
			{
				AuraServiceLib::IAuraSyncDevicePtr dev = devices->Item[i];
				AuraServiceLib::IAuraRgbLightCollectionPtr lights = dev->Lights;

				std::cout << dev->Name;
				std::cout << " : " + std::to_string(lights->Count) + " led(s)" << std::endl;
			}

			std::cout << std::endl;
			std::cout << "Starting Sync" << std::endl;
#endif

#ifdef SHOW_FPS
			int apply_count = 0;
			auto t_start = std::chrono::high_resolution_clock::now();
#endif

			std::vector<unsigned long> previous_led_values; // stores exisitng led values so we dont write to the leds if we dont have to
			bool first_run = true;


			while (1) {
				// --- v1.0/v1.1 (originali, richiesta/risposta via seriale) --------
				// wled_serial.write("l"); // request led data
				// json_string = wled_serial.readline(); // read response
				// --- v1.2 (formato stock, array di interi via seriale) ------------
				// (vedi versione precedente di questo file per il parsing intero)
				// -----------------------------------------------------------------------
				// v1.3 (2026-09-07): richiesta HTTP a /json/live al posto della
				// seriale. Risposta identica al vecchio formato {"leds":[...]}.
				try {
					json_string = fetchLiveLeds(hConnect);
				}
				catch (const std::exception& e) {
					std::cerr << "Errore richiesta a WLED: " << e.what() << std::endl;
					if (POLL_INTERVAL_MS > 0) {
						Sleep(POLL_INTERVAL_MS);
					}
					continue;
				}

				if (json_string.length() < 5 || json_string[0] != '{' || json_string.find('}') == std::string::npos) { // check if receivied valid json
					continue;
				}

				if (reader->parse(json_string.c_str(), json_string.c_str() + json_string.length(), &json_value, &json_err)) {

					if (!json_value.isMember("leds")) {
						continue;
					}

					Json::Value leds = json_value["leds"];
					int led_result_size = leds.size();

					if (led_result_size < 1) {
						continue;
					}

					if (previous_led_values.size() != led_result_size) {
						previous_led_values.assign(led_result_size, 0);
					}


					unsigned int led_index = 0;

					for (int i = 0; i < devices->Count; i++)
					{
						AuraServiceLib::IAuraSyncDevicePtr dev = devices->Item[i];
						AuraServiceLib::IAuraRgbLightCollectionPtr lights = dev->Lights;

						bool led_updated = false;

						for (int j = 0; j < lights->Count; j++)
						{
							if (led_index >= leds.size()) {
								break;
							}
							std::string color_value = leds[led_index].asString(); // "RRGGBB"
							std::string bgr_value = "0x00" + color_value.substr(4, 2) + color_value.substr(2, 2) + color_value.substr(0, 2); // Aura sdk expects 0x00BBGGRR instead of the supplied RRGGBB
							unsigned long ubgr_value = (unsigned long)strtol(bgr_value.c_str(), NULL, 16);

							if (previous_led_values[led_index] != ubgr_value || first_run) {
								AuraServiceLib::IAuraRgbLightPtr light = lights->Item[j];
								light->Color = ubgr_value;
								previous_led_values[led_index] = ubgr_value;
								led_updated = true;
							}

							led_index++;
						}
						// Apply colors that we have just set
						if (led_updated) {
							dev->Apply();
						}
#ifdef SHOW_FPS
						apply_count++;
						auto t_end = std::chrono::high_resolution_clock::now();
						if (std::chrono::duration<double, std::milli>(t_end - t_start).count() > 1000) {
							t_start = std::chrono::high_resolution_clock::now();
							std::cout << std::to_string(apply_count) + " fps" << std::endl;
							apply_count = 0;
						}
#endif
					}
				}
				if (first_run) {
					first_run = false;
				}
				if (POLL_INTERVAL_MS > 0) {
					Sleep(POLL_INTERVAL_MS);
				}
			}

		}
		// v1.1: se sdk.CreateInstance() fallisce (Aura Sync/Armoury Crate non
		// installato o servizio non registrato) stampiamo l'errore ed usciamo,
		// invece di lasciare l'exe aperto senza fare nulla.
		else {
			std::cerr << "Impossibile inizializzare l'Aura SDK 3.1 (HRESULT 0x" << std::hex << hr << ")." << std::endl;
			std::cerr << "Verifica che Aura Sync / Armoury Crate sia installato con la Lighting Service attiva." << std::endl;
			WinHttpCloseHandle(hConnect);
			WinHttpCloseHandle(hSession);
			return 1;
		}
		WinHttpCloseHandle(hConnect);
		WinHttpCloseHandle(hSession);
	}// Uninitialize COM
	::CoUninitialize();

	return 0;
}
