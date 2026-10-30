import ctypes
import time
import snap7
from snap7.type import SrvArea

server = snap7.server.Server()

# 100 bájtos buffer létrehozása a DB1 számára
db1_data = (ctypes.c_ubyte * 100)()

# DB1 regisztrálása a szerveren (SrvArea.DB, DB szám: 1, adatterület)
server.register_area(SrvArea.DB, 1, db1_data)

# Szerver indítása a 102-es porton
server.start_to("127.0.0.1", 102)

print("S7 Szerver fut, DB1 regisztrálva a 102-es porton... (Ctrl+C a leállításhoz)")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nSzerver leállítása...")
    server.stop()
