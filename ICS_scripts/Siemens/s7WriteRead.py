import snap7

client = snap7.client.Client()
client.connect("127.0.0.1", 0, 0, 102)
client.get_connected()
data = client.db_read(1, 0, 5)
print(data)
bytearray(b"\x00\x00\x00\x00\x00")
data[4] = 0b0000000001
print(data)
bytearray(b'\x00\x00\x00\x00\x01')
client.db_write(1, 0, data)
