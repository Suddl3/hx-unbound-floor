"""ssim keeps EMUCLK at 0; for meter/profile images in the simulator, make it read the sim's cycle count.
(Importing a kernel module such as nam_floor5p for this would also swap its kernel into nam_floor5.)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream import SHARC  # noqa: E402
sys.path.insert(0, SHARC)


def enable():
    import sasm
    import ssim
    code = sasm.UREG_CODE["EMUCLK"]
    cls = next(c for c in vars(ssim).values() if isinstance(c, type) and hasattr(c, "get") and hasattr(c, "set")
               and "cycles" in getattr(c.__init__, "__code__", type("x", (), {"co_names": ()})).co_names)
    if getattr(cls, "_emuclk_patched", False):
        return
    g0 = cls.get
    cls.get = lambda self, c: self.cycles & 0xFFFFFFFF if c == code else g0(self, c)
    cls._emuclk_patched = True
