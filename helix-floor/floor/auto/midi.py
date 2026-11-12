"""Tiny Windows MIDI (winmm via ctypes) for the Floor auto-tester: no extra packages."""
import ctypes, ctypes.wintypes as wt, threading, time

winmm = ctypes.WinDLL("winmm")
MIM_DATA, MIM_LONGDATA = 0x3C3, 0x3C4
CALLBACK_FUNCTION = 0x30000


class MIDIHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wt.DWORD), ("dwBytesRecorded", wt.DWORD),
                ("dwUser", ctypes.c_void_p), ("dwFlags", wt.DWORD), ("lpNext", ctypes.c_void_p),
                ("reserved", ctypes.c_void_p), ("dwOffset", wt.DWORD), ("dwReserved", ctypes.c_void_p * 8)]


def _names(kind):
    n = getattr(winmm, f"midi{kind}GetNumDevs")()
    out = []
    for i in range(n):
        buf = ctypes.create_string_buffer(256)
        getattr(winmm, f"midi{kind}GetDevCapsW")(i, buf, 256)
        out.append(ctypes.wstring_at(ctypes.addressof(buf) + 8))
    return out


def find(kind, name="Line 6 Helix"):
    for i, n in enumerate(_names(kind)):
        if n.startswith(name):
            return i
    raise RuntimeError(f"no MIDI {kind} '{name}': {_names(kind)}")


CB = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class Midi:
    def __init__(self, name="Line 6 Helix"):
        self.events = []          # (time, bytes)
        self.lock = threading.Lock()
        self.hout = wt.HANDLE(); self.hin = wt.HANDLE()
        r = winmm.midiOutOpen(ctypes.byref(self.hout), find("Out", name), 0, 0, 0)
        if r: raise RuntimeError(f"midiOutOpen {r}")
        self._cb = CB(self._on)
        r = winmm.midiInOpen(ctypes.byref(self.hin), find("In", name), self._cb, 0, CALLBACK_FUNCTION)
        if r: raise RuntimeError(f"midiInOpen {r}")
        self._bufs = []
        for _ in range(4):
            self._add_buf()
        winmm.midiInStart(self.hin)

    def _add_buf(self):
        data = ctypes.create_string_buffer(1024)
        h = MIDIHDR(); h.lpData = ctypes.cast(data, ctypes.c_void_p); h.dwBufferLength = 1024
        winmm.midiInPrepareHeader(self.hin, ctypes.byref(h), ctypes.sizeof(h))
        winmm.midiInAddBuffer(self.hin, ctypes.byref(h), ctypes.sizeof(h))
        self._bufs.append((h, data))

    def _on(self, h, msg, inst, p1, p2):
        now = time.time()
        if msg == MIM_DATA:
            v = p1 or 0
            b = bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF])
            with self.lock: self.events.append((now, b))
        elif msg == MIM_LONGDATA and p1:
            hdr = MIDIHDR.from_address(p1)
            if hdr.dwBytesRecorded:
                with self.lock: self.events.append((now, ctypes.string_at(hdr.lpData, hdr.dwBytesRecorded)))
            # (buffer re-adding from the callback is not allowed by winmm; sysex replies are rare)

    def short(self, *b):
        v = b[0] | (b[1] << 8 if len(b) > 1 else 0) | (b[2] << 16 if len(b) > 2 else 0)
        winmm.midiOutShortMsg(self.hout, v)

    def cc(self, num, val, ch=0): self.short(0xB0 | ch, num, val)
    def pc(self, prog, ch=0, setlist=2):         # setlist 2 = USER 1 (updates reset to a factory setlist)
        if setlist is not None: self.cc(32, setlist, ch)
        self.short(0xC0 | ch, prog)

    def sysex(self, data):
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        h = MIDIHDR(); h.lpData = ctypes.cast(buf, ctypes.c_void_p); h.dwBufferLength = len(data)
        winmm.midiOutPrepareHeader(self.hout, ctypes.byref(h), ctypes.sizeof(h))
        winmm.midiOutLongMsg(self.hout, ctypes.byref(h), ctypes.sizeof(h))
        time.sleep(0.05)
        winmm.midiOutUnprepareHeader(self.hout, ctypes.byref(h), ctypes.sizeof(h))

    def take(self):
        with self.lock:
            e, self.events = self.events, []
        return e

    def close(self):
        winmm.midiInStop(self.hin); winmm.midiInReset(self.hin)
        for h, _ in self._bufs:
            winmm.midiInUnprepareHeader(self.hin, ctypes.byref(h), ctypes.sizeof(h))
        winmm.midiInClose(self.hin); winmm.midiOutClose(self.hout)


if __name__ == "__main__":
    m = Midi()
    print("listening 3 s ...")
    time.sleep(3); print("idle:", [(round(t % 100, 2), b.hex()) for t, b in m.take()][:10])
    m.sysex([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7])   # universal identity request
    time.sleep(1.5); print("identity reply:", [b.hex() for t, b in m.take()])
    m.close()
