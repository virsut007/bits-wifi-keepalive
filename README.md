bits-wifi-keepalive
This lightweight Python script fully automates the login process for BITS WiFi. It silently runs in the background, automatically pinging the portal's keepalive endpoint and re-authenticating whenever your session expires.

Prerequisites
You will need Python 3.8 or higher installed on your system. You can download it directly from the official Python website if it is not already installed. The script also requires the requests library to handle network operations.

Installation and Setup
First, ensure you have the required library by running the following command in your terminal:
pip3 install requests

Second, download this repository by clicking the green "Code" button and selecting "Download ZIP", then extract the contents to your preferred directory. Alternatively, you can clone the repository directly via Git.

Third, open the config.py file in any text editor. You need to provide your campus credentials by updating the variables inside. Replace the USERNAME string with your BITS ID (for example, "F20XXXXXXX") and the PASSWORD string with your current network password.

Usage
To run the script normally and see the output directly in your terminal, simply execute:
python3 login.py
(Note: If you are on Windows, you may need to use python login.py instead.)

Running in the Background (Recommended)
To keep the script running continuously even after you close your terminal session, use the nohup command. Execute the following to start the background process:
nohup python3 login.py &> wifi.log &

You can check the script's activity and connection status at any time by viewing the generated log file:
cat wifi.log

When you need to stop the background process completely, you can terminate it with:
pkill -f login.py

How It Works
The BITS Pilani captive portal is designed to expire your session after approximately 14,000 seconds (roughly 3.9 hours). To prevent disconnections, this script proactively pings the keepalive URL every 13,000 seconds to reset the server's timer.

If a network drop occurs and the session does manage to expire, the script probes a plain HTTP website. This action forces the campus firewall to intercept the request, allowing the script to automatically submit your credentials via a POST request and restore your connection without any manual input.
