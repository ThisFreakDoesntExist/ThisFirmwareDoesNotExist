// Seed functions from Thumb code pointers stored in flash whose target starts with a push prologue.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;

public class MfSeed extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        long lo = 0x0800C000L, hi = lo + mem.getBlock("flash").getSize();
        int seeded = 0;
        for (long p = lo; p + 4 <= hi; p += 4) {
            long v = mem.getInt(toAddr(p)) & 0xffffffffL;
            if ((v & 1) == 0 || v < lo + 0x200 || v >= hi) continue;
            Address t = toAddr(v & ~1L);
            int h = mem.getShort(t) & 0xffff;
            boolean push = (h & 0xff00) == 0xb500 || (h & 0xfe00) == 0xb400 || h == 0xe92d;
            if (!push) continue;
            if (getFunctionAt(t) != null) continue;
            if (getInstructionAt(t) == null) {
                if (getDataContaining(t) != null) continue;
                try {
                    currentProgram.getProgramContext().setValue(currentProgram.getRegister("TMode"), t, t, java.math.BigInteger.ONE);
                } catch (Exception e) { continue; }
                disassemble(t);
            }
            if (createFunction(t, null) != null) seeded++;
        }
        println("seeded pointer targets: " + seeded);
    }
}
