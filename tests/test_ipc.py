import struct
import unittest
from unittest import mock

from better_qr_codes import ipc


def _response(payload: bytes, status: int = 1, message: str = "") -> bytes:
    status_bytes = ipc._int_field(1, status) + ipc._bytes_field(2, message.encode())
    any_bytes = ipc._bytes_field(1, b"type.googleapis.com/x") + ipc._bytes_field(2, payload)
    return ipc._bytes_field(2, status_bytes) + ipc._bytes_field(3, any_bytes)


class FakeKiCad:
    """REP0 side of NNG-over-IPC that records the requests it receives."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.outgoing = bytearray(b"\x00SP\x00" + struct.pack(">H", ipc._REP0) + b"\x00\x00")
        self.incoming = bytearray()
        self.closed = False

    def write(self, data):
        self.incoming.extend(data)
        if bytes(self.incoming[:8]) == b"\x00SP\x00" + struct.pack(">H", ipc._REQ0) + b"\x00\x00":
            del self.incoming[:8]
        while len(self.incoming) >= 9:
            length = struct.unpack(">Q", self.incoming[1:9])[0]
            if len(self.incoming) < 9 + length:
                break
            body = bytes(self.incoming[9:9 + length])
            del self.incoming[:9 + length]
            request_id, request = body[:4], body[4:]
            self.requests.append(ipc._parse(request))
            reply = request_id + self.replies.pop(0)
            self.outgoing.extend(b"\x01" + struct.pack(">Q", len(reply)) + reply)

    def read(self, size):
        chunk = bytes(self.outgoing[:size])
        del self.outgoing[:size]
        return chunk

    def close(self):
        self.closed = True


def _document(filename: str) -> bytes:
    return ipc._int_field(1, ipc._DOCTYPE_PCB) + ipc._bytes_field(4, filename.encode())


class IpcTests(unittest.TestCase):
    def _run(self, replies, board_filename="C:/work/b.kicad_pcb"):
        fake = FakeKiCad(replies)
        with mock.patch.object(ipc, "_connect", lambda timeout: ipc._Connection(fake)):
            ipc.interactive_move("1234-abcd", board_filename)
        return fake

    def test_sends_interactive_move_for_the_matching_board(self):
        documents = ipc._bytes_field(1, _document("a.kicad_pcb")) + ipc._bytes_field(1, _document("b.kicad_pcb"))
        fake = self._run([_response(documents), _response(b"")])

        self.assertTrue(fake.closed)
        open_docs, move = fake.requests
        self.assertEqual(
            ipc._parse(open_docs[2][0])[1][0],
            b"type.googleapis.com/kiapi.common.commands.GetOpenDocuments",
        )
        move_any = ipc._parse(move[2][0])
        self.assertEqual(move_any[1][0], b"type.googleapis.com/kiapi.board.commands.InteractiveMoveItems")
        command = ipc._parse(move_any[2][0])
        self.assertEqual(command[1][0], _document("b.kicad_pcb"))
        self.assertEqual(ipc._parse(command[2][0])[1][0], b"1234-abcd")
        self.assertTrue(ipc._parse(move[1][0])[2][0].startswith(b"better-qr-codes-"))

    def test_retries_while_kicad_is_busy(self):
        documents = ipc._bytes_field(1, _document("b.kicad_pcb"))
        fake = self._run([
            _response(b"", status=ipc._STATUS_BUSY),
            _response(documents),
            _response(b""),
        ])
        self.assertEqual(len(fake.requests), 3)

    def test_reports_api_errors(self):
        with self.assertRaises(ipc.IpcError):
            self._run([_response(b"", status=3, message="bad")])

    def test_varint_round_trip(self):
        for value in (0, 1, 127, 128, 300, 2**31, 2**63 - 1):
            self.assertEqual(ipc._parse(ipc._int_field(5, value)), {5: [value]})


if __name__ == "__main__":
    unittest.main()
