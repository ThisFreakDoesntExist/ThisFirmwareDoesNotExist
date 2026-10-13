// Decompile every function into one text file, for grepping. Args: <outfile>
// Each function starts with a line "######## <entry> <name>", so a search hit can be
// traced back to its function. Run it after MfSeed so vtable-only methods are included.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;

public class MfDecompileAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (PrintWriter pw = new PrintWriter(new FileWriter(a[0]))) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                pw.println("######## " + f.getEntryPoint() + " " + f.getName());
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                pw.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage());
            }
        }
    }
}
