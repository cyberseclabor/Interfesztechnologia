import snap7

client = snap7.client.Client()
client.connect("127.0.0.1", 0, 0, 102)
client.get_connected()
cpu_info = client.get_cpu_info()
print(cpu_info)
client.get_cpu_state()
client.get_pdu_length()
client.get_plc_datetime()
block_list = client.list_blocks()
print(block_list)
