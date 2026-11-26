# <img src='https://raw.githack.com/FortAwesome/Font-Awesome/master/svgs/solid/signal.svg' card_color='#40DBB0' width='50' height='50' style='vertical-align:bottom'/> Speedtest

Ask OVOS to run a speedtest.

## About

This skill runs an internet bandwidth test with [speedtest-cli](https://github.com/sivel/speedtest-cli), which uses speedtest.net.

The result depends on the network adapter of your device.

Examples for Raspberry Pi:
- Raspberry Pi 3 B onboard WiFi: max. ~40 Mbit/s, onboard LAN: max. ~100 Mbit/s
- Raspberry Pi 3 B+ onboard WiFi: max. ~100 Mbit/s, onboard LAN: max. ~225 Mbit/s

If your device runs on a Raspberry Pi 3 B connected over WiFi, the speedtest result stays at or below 40 Mbit/s, even if your internet connection supports more bandwidth.

## Examples

* "Hey mycroft, run a speedtest"

## Credits
- Original skill by Lukas Gangel (@luke5sky)
- Wifi speed animation by [flaticon.com](https://www.flaticon.com/free-animated-icon/wifi-speed_15591468)

## Category
Daily
Information
IoT
**Productivity**

## Tags
#internet
#speed
#bandwidth
