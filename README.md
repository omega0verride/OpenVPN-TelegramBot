# OpenVPN-TelegramBot
A simple bot that allows only you to connect a device to your openvpn server by specifying an ovpn file. Files can be uploaded as attachments.

This script runs on a machine with openvpn installed and allows you to connect the machine to the vpn from telegram.
You can upload ovpn files as attachments.

OpenVPN requires elevated privileges
To avoid any security issues by elevating this script I used:
```console
sudo chown root:root /usr/sbin/openvpn
sudo chmod 4775 /usr/sbin/openvpn
```
This will make openvpn run as root by default

The bot will respond only to commands coming from the specified user id

```python
authorized_user_ids = [737689398]


def validate_user(func: callable):
    def wrap(update, context: CallbackContext, *args):
        if update.message.from_user.id in authorized_user_ids:
            return func(update, context, *args)
        else:
            send_message("You do not have permissions to use this bot.", update, context)
            logger.error("User unauthorized!\nargs: " + str(update))

    return wrap
```


Commands:

```
/start /status /s           -> get current machine state
/connect /c                 -> connect using default ovpn file
/connect <filename>         -> connect specifying ovpn fle
/disconnect /d              -> disconect
/ip                         -> get current local and public ip
/process /p                 -> get the status of process that runs openvpn client
/getoutput /go              -> get the stdout file of the process
/list /ls /l                -> list all .ovpn files on the dir, you can upload others as attachments
/setdefault /sd <filename>  -> set default ovpn file
/default /df                -> check default ovpn file
```

---

Example adding the script as a service and enabling it to start on boot.
```console
cd /etc/systemd/system/
sudo nano telegrambot.service
```

Paste this config, change /path/to/script_folder/ and \<user\>

```bash
[Unit]
Description=Telegram Bot that controls OpenVPN service
After=multi-user.target
[Service]
Type=simple
User=<user>
Restart=always
WorkingDirectory=/path/to/script_folder/
ExecStart=/usr/bin/python3 /path/to/script_folder/main.py
StandardOutput=file:/path/to/script_folder/log.log
StandardError=file:/path/to/script_folder/err.log
[Install]
WantedBy=multi-user.target
```
```console
sudo systemctl daemon-reload
systemctl enable telegrambot.service
systemctl start telegrambot.service
systemctl status telegrambot.service
```
