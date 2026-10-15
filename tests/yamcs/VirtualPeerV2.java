package org.yamcs.tctm.ccsds;

import java.io.*;
import java.nio.*;
import java.util.*;
import java.util.concurrent.*;
import org.yamcs.YConfiguration;
import org.yamcs.commanding.PreparedCommand;
import org.yamcs.events.EventProducerFactory;
import org.yamcs.protobuf.Commanding.CommandId;
import org.yamcs.tctm.TcpTcDataLinkTest;
import org.yamcs.utils.TimeEncoding;
import com.google.gson.*;

/** Actual pinned FOP with an explicit deterministic executor adapter. No real MCU timing. */
public class VirtualPeerV2 {
    static class VirtualExecutor extends ScheduledThreadPoolExecutor {
        long now=0, seq=0;
        PriorityQueue<Task<?>> tasks=new PriorityQueue<>();
        VirtualExecutor(){super(1);}
        class Task<V> extends FutureTask<V> implements RunnableScheduledFuture<V> {
            long when, order;
            Task(Callable<V> c,long w){super(c);when=w;order=seq++;}
            public boolean isPeriodic(){return false;}
            public long getDelay(TimeUnit u){return u.convert(when-now,TimeUnit.MICROSECONDS);}
            public int compareTo(Delayed d){Task<?> t=(Task<?>)d;int c=Long.compare(when,t.when);return c==0?Long.compare(order,t.order):c;}
        }
        public void execute(Runnable r){schedule(r,0,TimeUnit.MICROSECONDS);}
        public ScheduledFuture<?> schedule(Runnable r,long delay,TimeUnit u){return schedule(Executors.callable(r,null),delay,u);}
        public <V> ScheduledFuture<V> schedule(Callable<V> c,long delay,TimeUnit u){Task<V> t=new Task<>(c,now+u.toMicros(delay));tasks.add(t);return t;}
        void advance(long target)throws Exception{
            if(target<now)throw new IllegalArgumentException("virtual clock cannot go backwards");
            int n=0;
            while(!tasks.isEmpty()&&tasks.peek().when<=target){
                Task<?> t=tasks.poll();if(t.isCancelled())continue;
                now=t.when;t.run();if(!t.isCancelled())t.get();if(++n>100000)throw new IllegalStateException("unbounded immediate task loop");
            }
            now=target;
        }
        Long next(){while(!tasks.isEmpty()&&tasks.peek().isCancelled())tasks.poll();return tasks.isEmpty()?null:tasks.peek().when;}
    }
    static class Monitor implements Cop1Monitor {
        int state=6;List<String>alerts=new ArrayList<>();
        public void stateChanged(int a,int b){state=b;}
        public void alert(AlertType a){alerts.add(a.toString());}
        public void suspended(int s){alerts.add("SUSPENDED "+s);}
        public void disabled(){alerts.add("DISABLED");}
    }
    VirtualExecutor ex;Monitor mon;Cop1UplinkPacketHandler<TcTransferFrame> peer;
    JsonObject reply(JsonObject q)throws Exception{
        String op=q.get("op").getAsString();JsonObject r=new JsonObject();
        if(op.equals("reset")){
            if(ex!=null)ex.shutdownNow();ex=new VirtualExecutor();mon=new Monitor();
            Map<String,Object> c=new HashMap<>();c.put("spacecraftId",42);c.put("maxFrameLength",q.get("max_frame").getAsInt());c.put("errorDetection","NONE");
            Map<String,Object> v=new HashMap<>();v.put("vcId",1);v.put("service","PACKET");v.put("clcwStream","clcw");v.put("useCop1",true);v.put("multiplePacketsPerFrame",true);v.put("slidingWindowWidth",q.get("window").getAsInt());c.put("virtualChannels",List.of(v));
            TcManagedParameters p=new TcManagedParameters(YConfiguration.wrap(c),null,null);
            peer=new Cop1UplinkPacketHandler<>("test","ctc1-virtual",p.getVcParams(1),ex);
            peer.addMonitor(mon);peer.setCommandHistoryPublisher(new TcpTcDataLinkTest.MyCmdHistPublisher(new Semaphore(0)));peer.setDataAvailableSemaphore(new Semaphore(0));
            peer.setT1Initial(q.get("t1_ms").getAsLong());peer.setTransmissionLimit(q.get("tx_limit").getAsInt());
            CompletableFuture<?> f=peer.setVs(q.get("vr").getAsInt());ex.advance(0);f.get();
            f=peer.initiateAD(false);ex.advance(0);f.get();
        }else if(op.equals("advance")){ex.advance(q.get("now_us").getAsLong());
        }else if(op.equals("send")){
            byte[] b=HexFormat.of().parseHex(q.get("hex").getAsString());
            PreparedCommand pc=new PreparedCommand(CommandId.newBuilder().setOrigin("ctc1-virtual").setGenerationTime(ex.now/1000).setSequenceNumber(q.get("index").getAsInt()).build());pc.setBinary(b);peer.sendCommand(pc);ex.advance(ex.now);
        }else if(op.equals("clcw")){peer.onCLCW((int)Long.parseLong(q.get("hex").getAsString(),16));ex.advance(ex.now);
        }else if(op.equals("pull")){
            TcTransferFrame t=peer.getFrame();ex.advance(ex.now);
            if(t!=null){r.addProperty("frame_hex",HexFormat.of().formatHex(t.getData()));r.addProperty("sequence",t.getVcFrameSeq());r.addProperty("commands",t.getCommands().size());}
        }else if(!op.equals("state"))throw new IllegalArgumentException(op);
        r.addProperty("state",mon.state);r.add("alerts",new Gson().toJsonTree(mon.alerts));r.addProperty("now_us",ex.now);
        Long next=ex.next();if(next!=null)r.addProperty("next_due_us",next);
        return r;
    }
    public static void main(String[] args)throws Exception{
        TimeEncoding.setUp();EventProducerFactory.setMockup(false);VirtualPeerV2 v=new VirtualPeerV2();
        try(BufferedReader in=new BufferedReader(new InputStreamReader(System.in));PrintWriter out=new PrintWriter(System.out,true)){
            String s;while((s=in.readLine())!=null){JsonObject q=JsonParser.parseString(s).getAsJsonObject();if(q.get("op").getAsString().equals("quit"))break;
                try{out.println(v.reply(q));}catch(Exception e){e.printStackTrace(System.err);JsonObject r=new JsonObject();r.addProperty("error",e.toString());out.println(r);}
            }
        }finally{if(v.ex!=null)v.ex.shutdownNow();}
    }
}
