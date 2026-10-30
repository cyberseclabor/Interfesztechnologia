import socket, struct, random

HOST, PORT = "127.0.0.1", 5020      # <- a sajat szerver

for i in range(200):
    fc   = random.randint(1, 0x2B)                      # function code
    data = bytes(random.getrandbits(8)
    for _ in range(random.randint(2, 8)))
    pdu  = struct.pack("B", fc) + data
    adu  = struct.pack(">HHHB", i, 0, len(pdu) + 1, 1) + pdu   # MBAP + PDU
    try:
        s = socket.create_connection((HOST, PORT), timeout=1)
        s.sendall(adu)
        s.recv(256)
        s.close()
    except OSError:
        pass
