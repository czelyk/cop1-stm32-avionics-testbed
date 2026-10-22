/* Persistent finite-FDU adapter around unchanged NASA cop1.c and tctf.c. */
#include "cop1.h"
#include "cfe.h"
#define LIMIT 8
#define PAYLOAD 256
volatile uint32 input[4], output[10];
uint8 incoming[261], slots[LIMIT][PAYLOAD+8], committed[PAYLOAD];
COP1_Clcw_t clcw;
static uint32 lengths[LIMIT], fifo[LIMIT], active, count, head, tail, commits;
static TCTF_ChannelService_t channel={TCTF_SERVICE_VCP,0,42,1,0,FALSE,FALSE};
int32 CFE_EVS_SendEvent(uint16 a,uint16 b,const char*c,...){(void)a;(void)b;(void)c;return 0;}
int32 CFE_PSP_MemSet(void*d,uint8 v,uint32 n){uint8*p=d;for(uint32 i=0;i<n;i++)p[i]=v;return 0;}
int32 CFE_PSP_MemCpy(void*d,const void*s,uint32 n){uint8*p=d;const uint8*q=s;for(uint32 i=0;i<n;i++)p[i]=q[i];return 0;}
static uint32 guards(void){for(uint32 j=0;j<LIMIT;j++)for(uint32 i=0;i<4;i++)if(slots[j][i]!=0xA5||slots[j][PAYLOAD+4+i]!=0xA5)return 0;return 1;}
void step(void){
 int32 ret=0;uint32 added=0,sink=0,slot=LIMIT;
 if(input[0]==0){
  active=input[3];count=head=tail=commits=0;
  for(uint32 j=0;j<LIMIT;j++){lengths[j]=0;for(uint32 i=0;i<PAYLOAD+8;i++)slots[j][i]=0xCC;for(uint32 i=0;i<4;i++){slots[j][i]=0xA5;slots[j][PAYLOAD+4+i]=0xA5;}}
  COP1_InitClcw(&clcw,1);clcw.Report=(uint8)input[2];
  if(active<1||active>LIMIT)ret=-30;
 }else if(input[0]==1){
  uint32 n=input[1],encoded=(((uint32)incoming[2]&3)<<8)|incoming[3];
  uint32 scid=(((uint32)incoming[0]&3)<<8)|incoming[1];
  if(n<19||n>261||encoded+1!=n||incoming[0]!=0||scid!=42||(incoming[2]>>2)!=1)ret=-10;
  else{
   for(uint32 j=0;j<active;j++)if(lengths[j]==0){slot=j;break;}
   ret=COP1_ProcessFrame(slot<LIMIT?&slots[slot][4]:0,&clcw,(TCTF_Hdr_t*)incoming,&channel);
   if(ret>0){lengths[slot]=(uint32)ret;fifo[tail]=slot;tail=(tail+1)%LIMIT;count++;}
  }
 }else if(input[0]==2&&count){
  slot=fifo[head];uint32 p=0,n=lengths[slot];
  while(p<n){
   if(n-p<14){ret=-20;break;}
   uint8*q=&slots[slot][4+p];uint32 size=7+(((uint32)q[4]<<8)|q[5]);
   if(q[0]!=0x10||q[1]!=0x42||(q[2]>>6)!=3||size<14||size>n-p){ret=-20;break;}
   p+=size;added++;
  }
  if(ret==0){for(uint32 i=0;i<n;i++)committed[i]=slots[slot][4+i];sink=n;commits+=added;lengths[slot]=0;head=(head+1)%LIMIT;count--;clcw.Flags&=(uint8)~0x10U;}
 }else if(input[0]!=2&&input[0]!=3)ret=-30;
 output[0]=(uint32)ret;output[1]=clcw.Report;output[2]=clcw.Flags;output[3]=count;output[4]=guards();output[5]=commits;output[6]=sink;output[7]=added;output[8]=count?lengths[fifo[head]]:0;output[9]=active;
}
