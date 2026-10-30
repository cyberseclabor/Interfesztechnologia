from pyModbusTCP.client import ModbusClient

c = ModbusClient(host="localhost", port=502, auto_open=True)
print(c.write_single_register(0, 1234))   # True, ha sikerült
print(c.read_holding_registers(0, 1))    # 1234
