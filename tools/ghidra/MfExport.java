// Post-analysis export: functions, defined strings with xrefs.
// Args: <outdir>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.StringDataInstance;
import java.io.*;

public class MfExport extends GhidraScript {
    @Override
    public void run() throws Exception {
        String out = getScriptArgs()[0];
        new File(out).mkdirs();
        Listing listing = currentProgram.getListing();
        ReferenceManager rm = currentProgram.getReferenceManager();
        try (PrintWriter pw = new PrintWriter(out + "/functions.tsv")) {
            for (Function f : listing.getFunctions(true)) {
                int callers = f.getCallingFunctions(monitor).size();
                pw.printf("%s\t%d\t%d\t%s%n", f.getEntryPoint(), f.getBody().getNumAddresses(), callers, f.getName());
            }
        }
        try (PrintWriter pw = new PrintWriter(out + "/strings.tsv")) {
            for (Data d : listing.getDefinedData(true)) {
                if (!StringDataInstance.isString(d)) continue;
                StringBuilder refs = new StringBuilder();
                for (Reference r : rm.getReferencesTo(d.getAddress())) {
                    Function f = getFunctionContaining(r.getFromAddress());
                    refs.append(r.getFromAddress()).append(f == null ? "" : "@" + f.getName()).append(' ');
                }
                String s = String.valueOf(d.getValue()).replace("\n", "\\n").replace("\t", "\\t");
                pw.printf("%s\t%s\t%s%n", d.getAddress(), s, refs.toString().trim());
            }
        }
        println("functions: " + listing.getFunctions(true).spliterator().getExactSizeIfKnown());
    }
}
