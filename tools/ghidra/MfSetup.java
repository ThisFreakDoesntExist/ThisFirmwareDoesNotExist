// Pre-analysis: add SRAM/peripheral blocks and seed functions from the vector table.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class MfSetup extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock flash = mem.getBlocks()[0];
        flash.setName("flash");
        flash.setWrite(false);
        flash.setExecute(true);
        MemoryBlock ram = mem.createUninitializedBlock("sram", toAddr(0x20000000L), 0x20000, false);
        ram.setRead(true); ram.setWrite(true); ram.setExecute(false);
        MemoryBlock ccm = mem.createUninitializedBlock("ccmram", toAddr(0x10000000L), 0x10000, false);
        ccm.setRead(true); ccm.setWrite(true);
        MemoryBlock periph = mem.createUninitializedBlock("periph", toAddr(0x40000000L), 0x20000000L, false);
        periph.setRead(true); periph.setWrite(true); periph.setVolatile(true);
        MemoryBlock scs = mem.createUninitializedBlock("scs", toAddr(0xE0000000L), 0x100000, false);
        scs.setRead(true); scs.setWrite(true); scs.setVolatile(true);

        Address base = toAddr(0x0800C000L);
        int n = 0;
        for (int i = 1; i < 114; i++) {
            long v = getInt(base.add(i * 4)) & 0xffffffffL;
            if ((v & 1) == 1 && v >= 0x0800C000L && v < 0x08080000L) {
                Address a = toAddr(v & ~1L);
                createDWord(base.add(i * 4));
                setThumb(a);
                disassemble(a);
                createFunction(a, i == 1 ? "Reset_Handler" : String.format("vec_%d_%08x", i, v & ~1L));
                n++;
            }
        }
        println("seeded vectors: " + n);
    }

    private void setThumb(Address a) throws Exception {
        var reg = currentProgram.getRegister("TMode");
        currentProgram.getProgramContext().setValue(reg, a, a, java.math.BigInteger.ONE);
    }
}
