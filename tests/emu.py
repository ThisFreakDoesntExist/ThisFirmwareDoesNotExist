"""Run pieces of a main image under Unicorn (Cortex-M4, Thumb)."""

from __future__ import annotations

import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_MCLASS, UC_MODE_THUMB, Uc
from unicorn import arm_const as arm

from freakpatch.patcher import MAIN_BASE

FLASH, FLASH_SIZE = 0x0800_0000, 0x8_0000
RAM, RAM_SIZE = 0x2000_0000, 0x2_0000
STACK_TOP = 0x2001_F000
RETURN = 0x0800_0100
"""Sentinel return address: unused bootloader flash, never executed."""
DATA_LOAD, DATA_SIZE = 0x0807_F75C, 0x2F4
"""Initialised data the reset handler copies from flash to RAM 0x20000000."""

PARAMS = 0x2001_C898
PARAM_INIT = 0x0800_EB10
PARAM_GET, PARAM_SET = 0x0802_3C2C, 0x0802_3C40
GROUP_COUNT = PARAMS + 0x24C
GROUP_SIZES, GROUP_KEYS, GROUP_NAMES = 0x2000_0408, 0x2000_03A8, 0x2000_0420
CC_MAP = PARAMS + 0x14C
RELEASE = 0x2001_DA72
DECAY_ID, RELEASE_ID = 0x602, 0x1400

REGS = {f"r{i}": getattr(arm, f"UC_ARM_REG_R{i}") for i in range(13)}
REGS |= {"sp": arm.UC_ARM_REG_SP, "lr": arm.UC_ARM_REG_LR, "pc": arm.UC_ARM_REG_PC}


class Emu:
    def __init__(self, payload: bytes, construct: bool = True) -> None:
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(FLASH, FLASH_SIZE)
        self.uc.mem_map(RAM, RAM_SIZE)
        self.uc.mem_write(MAIN_BASE, payload)
        self.write(RAM, payload[DATA_LOAD - MAIN_BASE : DATA_LOAD - MAIN_BASE + DATA_SIZE])
        self.uc.reg_write(arm.UC_ARM_REG_SP, STACK_TOP)
        if construct:
            self.call(PARAM_INIT, PARAMS, count=3_000_000)

    # memory
    def read(self, address: int, size: int) -> bytes:
        return bytes(self.uc.mem_read(address, size))

    def write(self, address: int, data: bytes) -> None:
        self.uc.mem_write(address, data)

    def read16(self, address: int) -> int:
        return struct.unpack("<H", self.read(address, 2))[0]

    def write16(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<H", value))

    def read32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def write32(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<I", value))

    def cstr(self, address: int) -> bytes:
        return self.read(address, 32).split(b"\0")[0]

    # parameters, through the stock getter and the constructed value tables
    def param(self, pid: int) -> int:
        return self.call(PARAM_GET, PARAMS, pid) & 0xFFFF

    def value_address(self, pid: int) -> int:
        return self.read32(PARAMS + 0x2C + (pid >> 8) * 4) + (pid & 0xFF) * 2

    def set_param(self, pid: int, value: int) -> None:
        self.write16(self.value_address(pid), value)

    @property
    def release(self) -> int:
        return self.read16(RELEASE)

    @release.setter
    def release(self, value: int) -> None:
        self.write16(RELEASE, value)

    # registers and execution
    def reg(self, name: str) -> int:
        return self.uc.reg_read(REGS[name])

    def set_regs(self, **values: int) -> None:
        for name, value in values.items():
            self.uc.reg_write(REGS[name], value)

    def regs(self) -> dict[str, int]:
        return {name: self.reg(name) for name in REGS if name != "pc"}

    def call(self, address: int, *args: int, count: int = 200_000) -> int:
        """Call the Thumb function at ``address``: up to four register arguments; returns r0."""
        self.set_regs(lr=RETURN | 1, **{f"r{i}": a for i, a in enumerate(args)})
        self.run(address, RETURN, count)
        return self.reg("r0")

    def run(self, start: int, until: int, count: int = 200_000) -> None:
        self.uc.emu_start(start | 1, until, count=count)
        if self.reg("pc") != until:
            raise AssertionError(f"stopped at {self.reg('pc'):#010x}, expected {until:#010x}")

    def stub(self, address: int, action=None) -> None:  # type: ignore[no-untyped-def]
        """Replace the function at ``address``: ``action(emu)`` runs, then it returns to lr."""

        def hook(uc: Uc, pc: int, size: int, user: object) -> None:
            if action:
                action(self)
            uc.reg_write(arm.UC_ARM_REG_PC, uc.reg_read(arm.UC_ARM_REG_LR) | 1)

        self.uc.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)
