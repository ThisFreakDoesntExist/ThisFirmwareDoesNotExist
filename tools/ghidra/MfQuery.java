// Query helper. Args: <outfile> then any of
//   dec:<addr>    decompile the function containing addr
//   xref:<addr>   list references to addr (with containing function)
//   str:<regex>   list defined strings matching regex, with xrefs
//   dis:<addr>:<n> disassemble n instructions from addr
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.StringDataInstance;
import java.io.*;
import java.util.regex.Pattern;

public class MfQuery extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        ReferenceManager rm = currentProgram.getReferenceManager();
        try (PrintWriter pw = new PrintWriter(new FileWriter(a[0]))) {
            for (int i = 1; i < a.length; i++) {
                String q = a[i];
                pw.println("\n######## " + q);
                if (q.startsWith("dec:")) {
                    Address ad = toAddr(Long.decode(q.substring(4)));
                    Function f = getFunctionContaining(ad);
                    if (f == null) {
                        if (getInstructionAt(ad) == null) {
                            try {
                                currentProgram.getProgramContext().setValue(currentProgram.getRegister("TMode"), ad, ad, java.math.BigInteger.ONE);
                            } catch (Exception e) { pw.println("ctx: " + e.getMessage()); }
                            disassemble(ad);
                        }
                        f = createFunction(ad, null);
                    }
                    if (f == null) { pw.println("no function"); continue; }
                    pw.println("// " + f.getName() + " @ " + f.getEntryPoint() + " size " + f.getBody().getNumAddresses()
                        + " callers " + f.getCallingFunctions(monitor));
                    DecompileResults r = di.decompileFunction(f, 120, monitor);
                    pw.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "decompile failed: " + r.getErrorMessage());
                } else if (q.startsWith("xref:")) {
                    Address ad = toAddr(Long.decode(q.substring(5)));
                    for (Reference r : rm.getReferencesTo(ad)) {
                        Function f = getFunctionContaining(r.getFromAddress());
                        pw.println(r.getFromAddress() + " " + r.getReferenceType() + " " + (f == null ? "-" : f.getName() + "@" + f.getEntryPoint()));
                    }
                } else if (q.startsWith("str:")) {
                    Pattern p = Pattern.compile(q.substring(4));
                    for (Data d : currentProgram.getListing().getDefinedData(true)) {
                        if (!StringDataInstance.isString(d)) continue;
                        String s = String.valueOf(d.getValue());
                        if (!p.matcher(s).find()) continue;
                        StringBuilder sb = new StringBuilder();
                        for (Reference r : rm.getReferencesTo(d.getAddress())) {
                            Function f = getFunctionContaining(r.getFromAddress());
                            sb.append(r.getFromAddress()).append(f == null ? "" : "@" + f.getEntryPoint()).append(' ');
                        }
                        pw.println(d.getAddress() + "\t" + s.replace("\n", "\\n") + "\t" + sb);
                    }
                } else if (q.startsWith("dis:")) {
                    String[] parts = q.split(":");
                    Address ad = toAddr(Long.decode(parts[1]));
                    int n = Integer.parseInt(parts[2]);
                    Instruction ins = getInstructionAt(ad);
                    if (ins == null) ins = getInstructionAfter(ad);
                    for (int k = 0; k < n && ins != null; k++, ins = ins.getNext())
                        pw.println(ins.getAddress() + "  " + ins);
                }
            }
        }
        di.dispose();
    }
}
