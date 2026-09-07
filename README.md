# WLEDAuraSync 2026 edition
Controlling Aura Sync devices through WLED

&nbsp;

## Description & Guide
1. **Python version**: controls the lights through [OpenRGB](https://openrgb.org/) instead of the Asus Aura SDK. On motherboards with "Gen 2" addressable RGB headers (e.g. AM5 boards like the ROG STRIX B650-A GAMING WIFI), the legacy Aura SDK V3.1 COM interface (`aura.sdk.1`/`AuraServiceLib`) simply never sees any device — `Enumerate()` returns 0 even with Armoury Crate/Aura Creator open and the Lighting Service running — because that header is driven by a newer USB controller the 2019-era SDK was never updated to recognize. Armoury Crate's own newer internal stack supports it, and so does OpenRGB (which ships a dedicated driver for it), so the Python version now talks to OpenRGB's SDK server instead. You need [OpenRGB](https://openrgb.org/) running with its SDK Server enabled (Settings > SDK Server > Server Enabled, default port 6742), and Armoury Crate closed (its `LightingService` must not be running, otherwise it and OpenRGB fight over the same hardware access).
   **C++ version**: still uses the legacy Aura SDK V3.1 for the lighting side (only the WLED transport was modernized, see point 2) — on the same "Gen 2 header" hardware it will report 0 devices found, same as the Python version did before this change. It hasn't been ported to OpenRGB yet.

2. The client app communicates with WLED over **WiFi** to get live led data, using WLED's built-in live-view feature (the same one used by the preview in WLED's own web UI): `GET /json/live` for the C++ version, `ws://<host>/ws` (`{"lv":true}`) for the Python version. No custom WLED firmware or serial/USB connection is required. Any recent stock WLED build works out of the box — just flash official WLED using the [Compile Guide](https://github.com/Aircoookie/WLED/wiki/Compiling-WLED) or install a stock release, then make sure your PC can reach the device's hostname or IP on the network (set a fixed IP or an mDNS name like `wled-lampada.local` in WLED's WiFi settings).

3. when running the app you should see a window similar to this (window hidden when starting from startup folder or with nowindow arg)

&nbsp;

<img width="675" alt="mainwindow" src="https://user-images.githubusercontent.com/981568/132116570-ef91a008-8963-4d43-8d87-9d9a19757111.png">

&nbsp;

4. the devices list are in order as far as I can tell, the way the SDK works is that it returns the total count of lights associated with a certain device but doesnt meen that all of them are used. in my case I had only 21 leds in the addressableStrip 1 and nothing connected to the addressableStrip 2, you can find that out either by counting or following the next step and keep trying till all the lights are working

5. To configure WLED to control your lights you must set WLED to the total amount of lights you want to control in order so for examble if I want to control the first 5 LEDs in the AddressableStrip 1, I must have WLED configured with atleast 29 leds. You can also use WLED segments and match the led numbers for better control. Try not to set the LEDs in WLED to more than you need because it will slow things down

6. After WLED is configured you can move the .exe file to your startup folder to run on desktop start (win + r then "shell:startup"), p.s. windows defender marked the exe I compiled as trojan which seems like a false positive. feel free to compile your own version

7. The exe runs with 3 optional command line arguments like this ".\WLEDAuraSync.exe wled-lampada.local 0 nowindow" (hostname or IP of your WLED device, a minimum delay in ms between HTTP requests - 0 for none, and the optional nowindow flag). The Python version only takes the hostname/IP as first argument, e.g. `python main.py wled-lampada.local`.

8. Resolving a `.local` mDNS hostname requires Windows to support mDNS on your network (this usually works out of the box, but if it doesn't, use the device's IP address directly - find it in the WLED app or your router). Expect a somewhat lower and more variable fps over WiFi than the old serial connection did (network latency depends on your router/WiFi), which is still plenty smooth for ambient lighting.

9. There is both a c++ and a python version available in the folders cpp and python respectively. I created the python version first but wanted to see if the Aura SDK was faster in c++, both languages gave the exact same fps. (I will probably maintain the c++ version more)

&nbsp;

## Build
### Python
1. install and open [OpenRGB](https://openrgb.org/), enable Settings > SDK Server > Server Enabled, and make sure Armoury Crate is closed (its LightingService must not be running)
2. in a venv:
```
pip install -r requirements.txt
python main.py wled-lampada.local
```
first argument is your WLED hostname/IP, optional second argument is OpenRGB's host if it's not running on the same PC (defaults to 127.0.0.1)

### C++
1. open in visual studio 2019 and build
2. uses WinHTTP (bundled with Windows) to talk to WLED, no extra library to build

## Final Result

The PC connected WLED is running in sync mode with the wall WLED
&nbsp;

![WLEDAuraSyncResult](https://user-images.githubusercontent.com/981568/132117298-40fce832-cdf8-4fef-a29a-9a799adc6b50.gif)


