#!/usr/bin/env python
# this script runs on a machine with openvpn installed and allows you to connect the machine to the vpn from telegram
# you can upload ovpn files as attachments

# openvpn requires elevated privileges
# to avoid any security issues by elevating this script I used:
# sudo chown root:root /usr/sbin/openvpn
# sudo chmod 4775 /usr/sbin/openvpn
# this will make openvpn run as root by default

import os
import socket

import json
import logging
import re
import time

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, JobQueue
import psutil
import glob
import subprocess
import threading

from requests import get

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

proc = None

# files will be created in the same path as the script
# independent of python location
base_path = os.path.dirname(__file__)
defaultFilePath = os.path.join(base_path, "default.txt")
processOutFilePath = os.path.join(base_path, "processOut.txt")

# the bot will respond only to commands coming from my account
authorized_user_ids = [737689398]


def validate_user(func: callable):
    def wrap(update, context: CallbackContext, *args):
        if update.message.from_user.id in authorized_user_ids:
            return func(update, context, *args)
        else:
            send_message("You do not have permissions to use this bot.", update, context)
            logger.error("User unauthorized!\nargs: " + str(update))

    return wrap


def get_status():
    return "CPU: {}%\nMemory: {}%\nUsed: {:.2f} MB\nAvailable: {:.2f} MB\nFree: {:.2f} MB\nTotal: {:.2f} MB".format(
        psutil.cpu_percent(),
        psutil.virtual_memory().percent,
        psutil.virtual_memory().used / 1000000,
        psutil.virtual_memory().available / 1000000,
        psutil.virtual_memory().free / 1000000,
        psutil.virtual_memory().total / 1000000)


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    pubip = get('https://api.ipify.org').text
    return ip, pubip


@validate_user
def ip(update, context: CallbackContext):
    ip = get_ip()
    send_message("Local IP: " + str(ip[0]) + "\nPublic IP: " + str(ip[1]), update, context)


def send_message(text, update, context: CallbackContext):
    update.message.reply_text(text)


@validate_user
def start(update, context: CallbackContext):
    send_message(get_status(), update, context)
    ip(update, context)


@validate_user
def help(update, context: CallbackContext):
    send_message(
        "/start /status /s -> get current machine state"
        "\n/connect /c -> connect using default ovpn file"
        "\n/connect <filename> -> connect specifying ovpn fle"
        "\n/disconnect /d -> disconect"
        "\n/ip -> get current local and public ip"
        "\n/process /p -> get the status of process that runs openvpn client"
        "\n/getoutput /go -> get the stdout file of the process"
        "\n/list /ls /l -> list all .ovpn files on the dir, you can upload others as attachments"
        "\n/setdefault /sd <filename> -> set default ovpn file"
        "\n/default /df -> check default ovpn file",
        update, context)


# openvpn requires elevated privileges
# to avoid any security issues by elevating this script I used:
# sudo chown root:root /usr/sbin/openvpn
# sudo chmod 4775 /usr/sbin/openvpn
# this will make openvpn run as root by default
@validate_user
def connect(update, context: CallbackContext, job_queue: JobQueue):
    cmd = ['openvpn']
    filename = None
    params = str(update.message.text).split(" ")
    if len(params) > 1:
        try:
            filename = params[1]
            if check_if_file_exists(filename):
                if not re.search("\.ovpn$", filename):
                    send_message("The file is not an ovpn client.", update, context)
                    return
            else:
                send_message(
                    "The file does not exist! Use /ls /l or /list to list available files.\nYou can upload other "
                    "ovpn files and they will automatically be added.", update, context)
                return
        except Exception as e:
            logger.error(str(e) + "Update: " + str(update))
            send_message("Invalid input! Use format /connect <filename> or /c file.ovpn", update, context)
            return
    else:
        filename = get_default_file(update, context)
        if filename is None:
            if len(get_client_files()):
                filename = get_client_files()[0]
            else:
                send_message("No client files available on the server. You can upload one as attachment.", update,
                             context)
                return

    cmd.append(os.path.join(base_path, filename))
    send_message("Connecting using file {}".format(filename), update, context)
    print(cmd)
    kill_processes()
    t = threading.Thread(target=run, args=(cmd, update, context))
    t.start()
    if proc is None or proc.returncode == 0 or proc.returncode == -9 or proc.returncode is None:  # 0 -> finished successfully; -9 killed by main
        schedule(update, context, job_queue, function=check_status, interval=3, count=4)


def run(cmd, update, context: CallbackContext):
    time_ = time.strftime("%d-%B %H:%M:%S")
    outfile = open(processOutFilePath, "w+")
    outfile.write(f"{time_} -> Connect\nFilename: {cmd[1]}\nCMD: {cmd}\n")
    outfile.close()
    outfile = open(processOutFilePath, "a")
    process = subprocess.Popen(cmd, stdout=outfile)
    global proc
    proc = process
    process.wait()
    outfile.close()
    if process.returncode != 0 and process.returncode != -9:  # 0 -> finished successfully; -9 killed by main
        output = open(processOutFilePath, "r").readlines()
        send_message("Failed to connnect! \nExit code: " + str(process.returncode) + "\nError: " + output[3], update,
                     context)
        send_message("For full output of error run /getoutput or /go to get the output file of the process.", update,
                     context)
    print(process)


def schedule(update, context: CallbackContext, job_queue, function: callable, interval: int = 2, count: int = 1):
    job_queue.run_once(lambda context_: function(update, context, job_queue, interval=interval, count=count),
                       interval)


def send_message_with_retry(update, context: CallbackContext, job_queue, chat_id, text, interval: int = 2,
                            count: int = 5):
    # after the traffic is routed through the VPN the API gets confused
    # the first message was always failing
    # sending an empty message fixed it
    # I am still leaving the retry logic just in case.
    try:
        context.bot.send_message(chat_id=chat_id, text="", timeout=1)
    except:
        pass
    try:
        context.bot.send_message(chat_id=chat_id, text=text, timeout=20)
        print(f"Message \"{text}\" sent.")
    except:
        print(f"Retry sending message \"{text}\"\nRetries left: {count}")
        if count <= 0:
            return
        job_queue.run_once(
            lambda context_: send_message_with_retry(update, context, job_queue, chat_id=chat_id, text=text,
                                                     interval=interval, count=count - 1),
            interval)


def check_status(update, context: CallbackContext, job_queue, interval: int = 2, count: int = 1):
    chat_id = update.effective_chat.id
    if proc is not None:
        if proc.returncode is None:  # this means the process is still running
            output = open(processOutFilePath, "r").readlines()[-1]
            if " ".join(output.split(" ")[-3:]) == "Initialization Sequence Completed\n":
                ip = get_ip()
                send_message_with_retry(update, context, job_queue, chat_id=chat_id,
                                        text="Connected!" + "\nLocal IP: " + str(ip[0]) + "\nPublic IP: " + str(ip[1]),
                                        interval=3,
                                        count=5)
                return
            else:
                print(f"Retry checking connection state... Retries left: {count}")
                if count <= 0:
                    send_message_with_retry(update, context, job_queue, chat_id=chat_id,
                                            text="Could not determine if connected! Check log with "
                                                 "/getoutput /go or check ip with /ip", interval=3,
                                            count=5)
                    return
                else:
                    schedule(update, context, job_queue, check_status, interval=interval, count=count - 1)
        else:
            pass  # the job failed but this is already handled by exit code at run()


@validate_user
def print_process(updater, context: CallbackContext):
    print(proc)
    send_message(str(proc), updater, context)


def kill_processes():
    global proc
    if proc is not None:
        proc.kill()
        proc = None
        # extra
    subprocess.Popen("pkill openvpn", shell=True)
    try:
        os.remove(processOutFilePath)
    except:
        pass


@validate_user
def disconnect(update, context: CallbackContext):
    send_message("Disconnected.\nPlease wait for the network to reset...", update, context)
    kill_processes()


def get_client_files():
    return [os.path.basename(s) for s in glob.glob(os.path.join(base_path, '*.ovpn'))]


@validate_user
def list_client_files(update, context: CallbackContext):
    files = ""
    for s in get_client_files():
        files += s + "\n"
    if files == "":
        files = "No files."
    send_message(files, update, context)


def check_if_file_exists(file):
    if file in get_client_files():
        return True
    return False


@validate_user
def get_default_file(update, context: CallbackContext):
    try:
        f = open(defaultFilePath, "r")
        file = f.readline()
        f.close()
    except FileNotFoundError:
        file = None
    send_message("Default file: {}".format(file), update, context)
    if not check_if_file_exists(file):
        send_message(
            "This file does not exist, another file will be picked automatically. \nYou can set another default file "
            "by /setdefault <filename> or /sd <filename>",
            update, context)
        file = None
    return file


@validate_user
def set_default_file(update, context: CallbackContext):
    try:
        filename = str(update.message.text).split(" ")[1]
    except:
        send_message("Invalid input! Use format /setdefault <filename> or /sd file.ovpn", update, context)
        return
    if check_if_file_exists(filename):
        if re.search("\.ovpn$", filename):
            open(defaultFilePath, "w+").close()
            open(defaultFilePath, "w+").write(filename)
            send_message("Successfully set {} as default file. Connect using /connect or /c".format(filename), update,
                         context)
        else:
            send_message("The file is not an ovpn client.", update, context)
    else:
        send_message("The file does not exist! Use /ls /l or /list to list available files.\nYou can upload other "
                     "ovpn files and they will automatically be added.", update, context)


@validate_user
def downloader(update, context: CallbackContext):
    filename_ = str(update.message.document.file_name)
    if re.search("\.ovpn$", filename_):
        with open(os.path.join(base_path, filename_), 'wb+') as f:
            context.bot.get_file(update.message.document).download(out=f)
        send_message("File uploaded successfully!", update, context)
    else:
        send_message("This is not an openvpn file!", update, context)


@validate_user
def upload_output(update, context: CallbackContext):
    try:
        f = open(processOutFilePath, 'r')
        chat_id = update.effective_chat.id
        return context.bot.send_document(chat_id, f)
    except FileNotFoundError:
        send_message("No output file found! Try connecting first.", update, context)


def error(update, context: CallbackContext):
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    updater = Updater("<APIKET>", use_context=True)
    dp = updater.dispatcher
    j = updater.job_queue

    dp.add_handler(CommandHandler(["start", "status", "s"], start))
    dp.add_handler(CommandHandler(["help", "h"], help))
    dp.add_handler(CommandHandler(["connect", "c"], lambda update, context: connect(update, context, j)))
    dp.add_handler(CommandHandler(["disconnect", "d"], disconnect))
    dp.add_handler(CommandHandler(["ip"], ip))
    dp.add_handler(CommandHandler(["getoutput", "go"], upload_output))
    dp.add_handler(CommandHandler(["list", "l", "ls"], list_client_files))
    dp.add_handler(CommandHandler(["setdefault", "sd"], set_default_file))
    dp.add_handler(CommandHandler(["default", "df"], get_default_file))
    dp.add_handler(CommandHandler(["process", "p"], print_process))

    updater.dispatcher.add_handler(MessageHandler(Filters.document, downloader))

    dp.add_error_handler(error)

    updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
