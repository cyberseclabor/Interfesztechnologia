import snap7

client = snap7.client.Client()
client.connect("127.0.0.1", 0, 0, 102)
buffer = client.db_get(1)
print(buffer)

cpu_info = client.get_cpu_info()
print(cpu_info)

print(client.get_cpu_state())

print(client.get_pdu_length())

print(client.get_plc_datetime())

block_list = client.list_blocks()
print(block_list)
