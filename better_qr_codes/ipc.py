"""Dependency-free client for the few KiCad IPC API calls the plugin needs.

KiCad's legacy SWIG API cannot start interactive tools, but the IPC API (KiCad 9+)
has ``InteractiveMoveItems``. The official ``kicad-python`` package needs pynng (a
compiled library) and protobuf, which a PCM package cannot install for a SWIG
plugin, so this module speaks the wire protocol directly:

- transport: NNG REQ0 over IPC (a Windows named pipe or a Unix socket);
- payload: protobuf ``kiapi`` messages, hand-encoded for the fields used here.

The IPC server must be enabled in KiCad (Preferences > Plugins > Enable KiCad API).
Every function raises ``IpcError`` on failure so callers can fall back quietly.
"""

from __future__ import annotations

import glob
import os
import platform
import random
import socket
import struct
import tempfile
import time

_REQ0 = 0x30
_REP0 = 0x31
_STATUS_OK = 1
_STATUS_NOT_READY = 4
_STATUS_BUSY = 7
_DOCTYPE_PCB = 3
_TYPE_PREFIX = "type.googleapis.com/"


class IpcError(RuntimeError):
    """The KiCad IPC API is unavailable or rejected a request."""


# --- protobuf wire format ---------------------------------------------------

def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _bytes_field(number: int, data: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(data)) + data


def _int_field(number: int, value: int) -> bytes:
    return _varint(number << 3) + _varint(value)


def _parse(data: bytes) -> dict[int, list]:
    """Decode one message level into {field number: [int or bytes, ...]}."""
    fields: dict[int, list] = {}
    index = 0

    def read_varint():
        nonlocal index
        result = shift = 0
        while True:
            if index >= len(data):
                raise IpcError("Truncated protobuf message")
            byte = data[index]
            index += 1
            result |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return result

    while index < len(data):
        key = read_varint()
        number, wire_type = key >> 3, key & 7
        if wire_type == 0:
            value = read_varint()
        elif wire_type == 2:
            length = read_varint()
            value = data[index:index + length]
            index += length
        elif wire_type == 1:
            value, index = data[index:index + 8], index + 8
        elif wire_type == 5:
            value, index = data[index:index + 4], index + 4
        else:
            raise IpcError(f"Unsupported protobuf wire type {wire_type}")
        fields.setdefault(number, []).append(value)
    return fields


def _request(type_name: str, payload: bytes, client_name: str, token: str = "") -> bytes:
    header = _bytes_field(1, token.encode()) + _bytes_field(2, client_name.encode())
    message = _bytes_field(1, (_TYPE_PREFIX + type_name).encode()) + _bytes_field(2, payload)
    return _bytes_field(1, header) + _bytes_field(2, message)


def _response_payload(data: bytes) -> bytes:
    response = _parse(data)
    status = _parse(response.get(2, [b""])[0])
    code = status.get(1, [0])[0]
    if code != _STATUS_OK:
        message = status.get(2, [b""])[0].decode("utf-8", "replace")
        error = IpcError(f"KiCad API status {code}: {message}")
        error.code = code
        raise error
    message = _parse(response.get(3, [b""])[0])
    return message.get(2, [b""])[0]


# --- NNG REQ0 over IPC ------------------------------------------------------

class _Connection:
    def __init__(self, stream):
        self._stream = stream
        self._request_id = random.getrandbits(31)
        self._write(b"\x00SP\x00" + struct.pack(">H", _REQ0) + b"\x00\x00")
        header = self._read(8)
        if header[:4] != b"\x00SP\x00" or struct.unpack(">H", header[4:6])[0] != _REP0:
            raise IpcError("Unexpected NNG handshake from KiCad")

    def call(self, request: bytes) -> bytes:
        self._request_id = (self._request_id + 1) & 0x7FFFFFFF
        request_id = struct.pack(">I", self._request_id | 0x80000000)
        body = request_id + request
        self._write(b"\x01" + struct.pack(">Q", len(body)) + body)
        while True:
            kind = self._read(1)
            length = struct.unpack(">Q", self._read(8))[0]
            reply = self._read(length)
            # Replies to stale request IDs (none expected) are skipped.
            if kind == b"\x01" and reply[:4] == request_id:
                return reply[4:]

    def close(self):
        try:
            self._stream.close()
        except OSError:
            pass

    def _write(self, data: bytes):
        self._stream.write(data)

    def _read(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._stream.read(size - len(chunks))
            if not chunk:
                raise IpcError("KiCad closed the API connection")
            chunks.extend(chunk)
        return bytes(chunks)


class _SocketStream:
    def __init__(self, path: str, timeout: float):
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.settimeout(timeout)
        self._socket.connect(path)

    def write(self, data: bytes):
        self._socket.sendall(data)

    def read(self, size: int) -> bytes:
        return self._socket.recv(size)

    def close(self):
        self._socket.close()


def _socket_candidates() -> list[str]:
    """Return possible API endpoints, this process's own instance first.

    KiCad names its socket ``api.sock`` or, when that exists, ``api-<pid>.sock``.
    The plugin runs inside KiCad, so ``os.getpid()`` is KiCad's process ID.
    """
    pid_name = f"api-{os.getpid()}.sock"
    configured = os.environ.get("KICAD_API_SOCKET")
    candidates = [configured.removeprefix("ipc://")] if configured else []
    if platform.system() == "Windows":
        root = "\\\\.\\pipe\\"
        try:
            pipes = os.listdir(root)
        except OSError:
            pipes = []
        names = [
            name for name in pipes
            if name.lower().endswith(".sock") and "kicad" in name.lower()
            and os.path.basename(name).startswith("api")
        ]
        names.sort(key=lambda name: (not name.endswith(pid_name), name))
        candidates += [root + name for name in names]
        candidates.append(root + os.path.join(tempfile.gettempdir(), "kicad", "api.sock"))
    else:
        directories = ["/tmp/kicad", os.path.join(tempfile.gettempdir(), "kicad")]
        home = os.environ.get("HOME")
        if home:
            directories.append(f"{home}/.var/app/org.kicad.KiCad/cache/tmp/kicad")
        for directory in directories:
            paths = glob.glob(os.path.join(directory, "api*.sock"))
            paths.sort(key=lambda path: (not path.endswith(pid_name), path))
            candidates += paths
    return list(dict.fromkeys(candidates))


def _connect(timeout: float) -> _Connection:
    errors = []
    for path in _socket_candidates():
        try:
            if path.startswith("\\\\.\\pipe\\"):
                stream = open(path, "r+b", buffering=0)
            else:
                stream = _SocketStream(path, timeout)
            return _Connection(stream)
        except (OSError, IpcError) as error:
            errors.append(f"{path}: {error}")
    raise IpcError("KiCad API server not found. " + "; ".join(errors))


# --- commands ---------------------------------------------------------------

def interactive_move(item_uuid: str, board_filename: str = "", *, timeout: float = 5.0) -> None:
    """Put a board item in the user's hand, like KiCad's Move tool.

    Must not be called on KiCad's main thread: the server answers from it.
    """
    client_name = "better-qr-codes-" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))
    connection = _connect(timeout)
    try:
        documents = _call_with_retry(
            connection,
            "kiapi.common.commands.GetOpenDocuments",
            _int_field(1, _DOCTYPE_PCB),
            client_name,
            timeout,
        )
        specifiers = _parse(documents).get(1, [])
        if not specifiers:
            raise IpcError("KiCad reports no open board")
        document = _matching_document(specifiers, board_filename)
        _call_with_retry(
            connection,
            "kiapi.board.commands.InteractiveMoveItems",
            _bytes_field(1, document) + _bytes_field(2, _bytes_field(1, item_uuid.encode())),
            client_name,
            timeout,
        )
    finally:
        connection.close()


def _matching_document(specifiers: list[bytes], board_filename: str) -> bytes:
    wanted = os.path.basename(board_filename)
    for specifier in specifiers:
        filename = _parse(specifier).get(4, [b""])[0].decode("utf-8", "replace")
        if wanted and os.path.basename(filename) == wanted:
            return specifier
    return specifiers[0]


def _call_with_retry(connection, type_name, payload, client_name, timeout) -> bytes:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return _response_payload(connection.call(_request(type_name, payload, client_name)))
        except IpcError as error:
            busy = getattr(error, "code", None) in (_STATUS_BUSY, _STATUS_NOT_READY)
            if not busy or time.monotonic() > deadline:
                raise
            time.sleep(0.05)
