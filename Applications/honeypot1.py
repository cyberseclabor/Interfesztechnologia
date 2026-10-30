import argparse
import asyncio
import json
import logging
import signal
from datetime import datetime, timezone

# Alapértelmezett portok (1024 felettiek, így nem kell root)
DEFAULT_PORTS = {
    2222: "ssh",
    2121: "ftp",
    2323: "telnet",
    8080: "http",
}

MAX_READ = 4096          # egy olvasás max. mérete (bájt)
MAX_TOTAL = 64 * 1024    # egy kapcsolatból max. ennyit naplózunk
READ_TIMEOUT = 30        # mp tétlenség után bontunk
MAX_CONNECTIONS = 200    # egyidejű kapcsolatok felső korlátja

log = logging.getLogger("honeypot")
active = asyncio.Semaphore(MAX_CONNECTIONS)


def event(**fields):
    """Egy esemény kiírása JSON-sorként."""
    fields["ts"] = datetime.now(timezone.utc).isoformat()
    log.info(json.dumps(fields, ensure_ascii=False))


def clean(data: bytes) -> str:
    """Nyers bájtok biztonságos, olvasható szöveggé alakítása."""
    return data.decode("utf-8", errors="backslashreplace").strip()


async def read_chunk(reader, timeout=READ_TIMEOUT) -> bytes:
    """Nyers adatdarab olvasása (pl. SSH-hoz)."""
    data = await asyncio.wait_for(reader.read(MAX_READ), timeout)
    if not data:
        raise ConnectionResetError
    return data


async def read_line(reader, timeout=READ_TIMEOUT) -> bytes:
    """Egy sor olvasása (\\n-ig); a túl hosszú sorokat csonkolja."""
    try:
        data = await asyncio.wait_for(reader.readline(), timeout)
    except (asyncio.LimitOverrunError, ValueError):
        data = await asyncio.wait_for(reader.read(MAX_READ), timeout)
    if not data:
        raise ConnectionResetError
    return data[:MAX_READ]


# ---------- Hamis szolgáltatások ----------

async def fake_ssh(reader, writer, ctx):
    writer.write(b"SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.5\r\n")
    await writer.drain()
    total = 0
    while total < MAX_TOTAL:
        data = await read_chunk(reader)
        total += len(data)
        event(type="data", **ctx, raw=clean(data)[:500])


async def fake_ftp(reader, writer, ctx):
    writer.write(b"220 (vsFTPd 3.0.5)\r\n")
    await writer.drain()
    user = None
    for _ in range(20):
        line = clean(await read_line(reader))
        cmd, _, arg = line.partition(" ")
        cmd = cmd.upper()
        if cmd == "USER":
            user = arg
            writer.write(b"331 Please specify the password.\r\n")
        elif cmd == "PASS":
            event(type="login_attempt", **ctx, username=user, password=arg)
            writer.write(b"530 Login incorrect.\r\n")
        elif cmd == "QUIT":
            writer.write(b"221 Goodbye.\r\n")
            await writer.drain()
            return
        else:
            event(type="command", **ctx, command=line[:500])
            writer.write(b"530 Please login with USER and PASS.\r\n")
        await writer.drain()


async def fake_telnet(reader, writer, ctx):
    writer.write(b"\r\nUbuntu 24.04.1 LTS\r\n")
    for _ in range(3):
        writer.write(b"login: ")
        await writer.drain()
        user = clean(await read_line(reader))
        writer.write(b"Password: ")
        await writer.drain()
        password = clean(await read_line(reader))
        event(type="login_attempt", **ctx, username=user[:200], password=password[:200])
        await asyncio.sleep(1.5)  # valósághű késleltetés
        writer.write(b"\r\nLogin incorrect\r\n")
    await writer.drain()


async def fake_http(reader, writer, ctx):
    first_line = clean(await read_line(reader))
    headers = {}
    for _ in range(100):  # fejlécek az üres sorig
        line = clean(await read_line(reader))
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()[:300]
    body = b""
    try:
        length = min(int(headers.get("content-length", 0)), MAX_READ)
        if length > 0:
            body = await asyncio.wait_for(reader.readexactly(length), READ_TIMEOUT)
    except (ValueError, asyncio.IncompleteReadError):
        pass
    event(type="http_request", **ctx, request=first_line[:500],
          user_agent=headers.get("user-agent"),
          authorization=headers.get("authorization"),
          body=clean(body)[:1000])
    page = (b"<html><head><title>Admin Login</title></head><body>"
            b"<h2>Router Administration</h2>"
            b"<form method='POST' action='/login'>"
            b"User: <input name='user'><br>Password: <input type='password' name='pass'><br>"
            b"<input type='submit' value='Login'></form></body></html>")
    writer.write(b"HTTP/1.1 200 OK\r\n"
                 b"Server: Apache/2.4.58 (Ubuntu)\r\n"
                 b"Content-Type: text/html\r\n"
                 b"Content-Length: " + str(len(page)).encode() + b"\r\n"
                 b"Connection: close\r\n\r\n" + page)
    await writer.drain()


SERVICES = {"ssh": fake_ssh, "ftp": fake_ftp, "telnet": fake_telnet, "http": fake_http}


# ---------- Kapcsolatkezelés ----------

def make_handler(port, service):
    async def handler(reader, writer):
        peer = writer.get_extra_info("peername") or ("?", 0)
        ctx = {"src_ip": peer[0], "src_port": peer[1], "dst_port": port, "service": service}
        if active.locked():
            writer.close()
            return
        async with active:
            event(type="connect", **ctx)
            try:
                await SERVICES[service](reader, writer, ctx)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                pass
            except Exception as e:  # sose álljon le egy hibás kliens miatt
                event(type="error", **ctx, error=repr(e))
            finally:
                event(type="disconnect", **ctx)
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
    return handler


async def main(ports, host):
    servers = []
    for port, service in ports.items():
        srv = await asyncio.start_server(make_handler(port, service), host, port)
        servers.append(srv)
        log.info(json.dumps({"type": "listening", "port": port, "service": service}))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    for srv in servers:
        srv.close()
        await srv.wait_closed()


def parse_ports(items):
    ports = {}
    for item in items:
        port, _, service = item.partition(":")
        if service not in SERVICES:
            raise SystemExit(f"Ismeretlen szolgáltatás: {service!r} (lehet: {', '.join(SERVICES)})")
        ports[int(port)] = service
    return ports


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Egyszerű Python honeypot")
    ap.add_argument("--ports", nargs="+", metavar="PORT:SZOLG",
                    help="pl. 2222:ssh 8080:http (szolgáltatások: ssh, ftp, telnet, http)")
    ap.add_argument("--host", default="0.0.0.0", help="figyelt cím (alap: 0.0.0.0)")
    ap.add_argument("--log", default="honeypot.log", help="naplófájl (JSON-sorok)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.FileHandler(args.log), logging.StreamHandler()])

    ports = parse_ports(args.ports) if args.ports else DEFAULT_PORTS
    asyncio.run(main(ports, args.host))
