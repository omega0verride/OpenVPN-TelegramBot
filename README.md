# OpenVPN-TelegramBot
A simple bot that allows only you to connect a device to your openvpn server by specifying an ovpn file. Files can be uploaded as attachments.

This script runs on a machine with openvpn installed and allows you to connect the machine to the vpn from telegram.
You can upload ovpn files as attachments.

OpenVPN requires elevated privileges
To avoid any security issues by elevating this script I used:
sudo chown root:root /usr/sbin/openvpn
sudo chmod 4775 /usr/sbin/openvpn
This will make openvpn run as root by default

The bot will respond only to commands coming from the specified user id

```
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
