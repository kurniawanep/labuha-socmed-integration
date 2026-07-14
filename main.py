import socket
import sys
import whatsapp_listener

# TCP port used to prevent duplicate instances
LOCK_PORT = 43210
lock_socket = None

def acquire_lock():
    global lock_socket
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', LOCK_PORT))
        # Keep socket open during execution
    except socket.error:
        print("Another instance of the bot is already running. Exiting.")
        sys.exit(99)

if __name__ == "__main__":
    acquire_lock()
    whatsapp_listener.run()

