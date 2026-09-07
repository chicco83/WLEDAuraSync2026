// ============================================================================
// WLEDAuraSync.cpp
// Versioning:
//   v1.1 - 2026-09-07 - Fix crash immediato all'avvio.
//          Causa: wled_serial.open() e le chiamate all'SDK Aura Sync 3.1
//          (SwitchMode/Enumerate) sollevano eccezioni C++ (serial::IOException
//          / _com_error) quando la porta COM di default non esiste o il
//          servizio Aura Sync/Armoury Crate non e' raggiungibile. Prima non
//          venivano intercettate -> std::terminate() -> crash immediato
//          dell'eseguibile senza nessun messaggio. Ora vengono gestite con
//          try/catch e viene stampato un messaggio diagnostico chiaro prima
//          di uscire in modo controllato (vedi sezioni commentate "v1.0").
//   v1.0 - baseline originale (Shady Nawara, WLEDAuraSync2021)
// ============================================================================
#import "libid:F1AA5209-5217-4B82-BA7E-A68198999AFA"
#include "serial/serial.h"
#include <iostream>
#include "json/json.h"
#include <comdef.h> // necessario per intercettare le eccezioni _com_error dell'SDK Aura

//#define SHOW_FPS
#define SHOW_INFO

#ifdef SHOW_FPS
#include <chrono>
#include <ctime>
#endif


serial::Serial wled_serial;

void cleanup()
{
	if (wled_serial.isOpen()) {
		wled_serial.close();
	}
	::CoUninitialize();
}

int main(int argc, char** argv)
{
	//////////
	// User Configurable Section or through command line
	//////////
	std::string WLEDCOMPORT = "COM5";
	int WLEDBAUDRATE = 115200;
	//
	//// End of User Configurable Section
	///////////

	if (argc > 1) {
		WLEDCOMPORT = std::string(argv[1]);
		if (argc > 2) {
			WLEDBAUDRATE = std::stoi(argv[2]);
		}
		if (argc > 3 && std::string(argv[3]) == "nowindow") {
			HWND consoleWindow = GetConsoleWindow(); // hide console window
			ShowWindow(consoleWindow, 0);
		}
	}

	wled_serial.setPort(WLEDCOMPORT);
	wled_serial.setBaudrate(WLEDBAUDRATE);

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
		// --- v1.0 (originale, causava crash immediato) ---------------------
		// wled_serial.open(); // open serial
		// if (wled_serial.isOpen()) {
		// #ifdef SHOW_INFO
		// 	std::cout << "Connected to WLED" << std::endl;
		// #endif
		// }
		// else {
		// 	return 1;
		// }
		// ---------------------------------------------------------------------
		// v1.1 (2026-09-07): serial::Serial::open() non ritorna un errore,
		// lancia un'eccezione (serial::IOException) se la porta COM indicata
		// (o quella di default se l'exe viene avviato senza argomenti) non
		// esiste, e' gia' in uso o il dispositivo non e' collegato. Senza
		// try/catch questa eccezione non gestita terminava subito il
		// programma: da fuori sembrava che "l'exe non si avviasse".
		try {
			wled_serial.open(); // open serial
		}
		catch (const std::exception& e) {
			std::cerr << "Errore apertura porta seriale " << WLEDCOMPORT << ": " << e.what() << std::endl;
			std::cerr << "Verifica che il dispositivo WLED sia collegato e che la porta COM passata come primo argomento sia corretta (es. WLEDAuraSync.exe COM3 115200)." << std::endl;
			return 1;
		}

		if (wled_serial.isOpen()) {
#ifdef SHOW_INFO
			std::cout << "Connected to WLED" << std::endl;
#endif
		}
		else {
			return 1;
		}

		// uninitialize on exit
		const int exit_callback = std::atexit(cleanup);

		// Create SDK instance
		AuraServiceLib::IAuraSdkPtr sdk = nullptr;
		hr = sdk.CreateInstance(__uuidof(AuraServiceLib::AuraSdk), nullptr, CLSCTX_INPROC_SERVER);
		if (SUCCEEDED(hr))
		{
			AuraServiceLib::IAuraSyncDeviceCollectionPtr devices;

			// --- v1.0 (originale, causava crash immediato) ---------------
			// sdk->SwitchMode();
			// devices = sdk->Enumerate(0); // 0 means ALL
			// -----------------------------------------------------------------
			// v1.1 (2026-09-07): IAuraSdkPtr e' uno smart pointer COM (_com_ptr_t)
			// che per default lancia un'eccezione _com_error se la chiamata
			// fallisce (es. servizio Aura Sync/Armoury Crate non in esecuzione,
			// o la "Lighting Service" non e' attiva). Anche qui l'eccezione
			// non gestita causava il crash immediato dell'exe. La SDK Aura
			// usata resta la V3.1 (e' tuttora l'ultima disponibile sul sito
			// Asus), il problema non era la versione dell'SDK ma la gestione
			// mancante degli errori quando il servizio non e' raggiungibile.
			try {
				// Acquire control
				sdk->SwitchMode();
				// Enumerate all devices
				devices = sdk->Enumerate(0); // 0 means ALL
			}
			catch (const _com_error& e) {
				std::cerr << "Errore comunicazione con Aura Sync SDK 3.1: " << (const char*)e.ErrorMessage() << " (HRESULT 0x" << std::hex << e.Error() << ")" << std::endl;
				std::cerr << "Verifica che il servizio Aura Sync / Armoury Crate sia installato e in esecuzione (Lighting Service attivo)." << std::endl;
				return 1;
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
				wled_serial.write("l"); // request led data
				json_string = wled_serial.readline(); // read response
				if (json_string.length() < 5 || json_string[0] != '{' || json_string[json_string.length() - 3] != '}') { // check if receivied valid json
					continue;
				}

				if (reader->parse(json_string.c_str(), json_string.c_str() + json_string.length(), &json_value, &json_err)) {

					if (!json_value.isMember("leds")) {
						continue;
					}

					json_value = json_value["leds"];
					int led_result_size = json_value.size();

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
							if (led_index >= json_value.size()) {
								break;
							}
							std::string color_value = json_value[led_index].asString();
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
			}

		}
		// v1.1 (2026-09-07): prima non c'era nessun "else" qui: se
		// sdk.CreateInstance() falliva (Aura Sync/Armoury Crate non
		// installato o servizio non registrato) l'exe restava aperto senza
		// fare nulla e senza nessun messaggio, dando l'impressione di un
		// eseguibile "morto". Ora viene stampato l'errore e il programma
		// esce subito.
		else {
			std::cerr << "Impossibile inizializzare l'Aura SDK 3.1 (HRESULT 0x" << std::hex << hr << ")." << std::endl;
			std::cerr << "Verifica che Aura Sync / Armoury Crate sia installato con la Lighting Service attiva." << std::endl;
			return 1;
		}
	}// Uninitialize COM
	::CoUninitialize();

	return 0;
}