package org.yamcs.tctm.ccsds;
import java.io.*;import java.util.*;import org.yamcs.YConfiguration;import com.google.gson.*;
/** Independent pinned Yamcs TM/CRC/OCF verification of saved target frames. */
public class TMVerifier {
 public static void main(String[] args)throws Exception{
  Map<String,Object> c=new HashMap<>();c.put("spacecraftId",42);c.put("frameLength",280);c.put("errorDetection","CRC16");
  Map<String,Object> v=new HashMap<>();v.put("vcId",1);v.put("service","PACKET");v.put("packetPreprocessorClassName","org.yamcs.tctm.GenericPacketPreprocessor");c.put("virtualChannels",List.of(v));
  TmFrameDecoder d=new TmFrameDecoder(new TmManagedParameters(YConfiguration.wrap(c),null,null));
  BufferedReader in=new BufferedReader(new InputStreamReader(System.in));PrintWriter out=new PrintWriter(System.out,true);String line;
  while((line=in.readLine())!=null){byte[] raw=HexFormat.of().parseHex(line);JsonObject r=new JsonObject();
   try{TmTransferFrame f=d.decode(raw,0,raw.length);r.addProperty("accepted",true);r.addProperty("clcw",String.format("%08x",f.getOcf()));r.addProperty("data_start",f.getDataStart());r.addProperty("data_end",f.getDataEnd());r.addProperty("first_header",f.getFirstHeaderPointer());}
   catch(Exception e){r.addProperty("accepted",false);r.addProperty("error",e.toString());}out.println(r);
  }
 }
}
