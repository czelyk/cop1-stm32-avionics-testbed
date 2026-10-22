
#ifndef PROBE_CFE_H
#define PROBE_CFE_H
#include "io_lib.h"
#define CFE_EVS_ERROR 1
#define CFE_EVS_INFORMATION 2
int32 CFE_EVS_SendEvent(uint16 id, uint16 type, const char* format, ...);
int32 CFE_PSP_MemSet(void* dst, uint8 value, uint32 n);
int32 CFE_PSP_MemCpy(void* dst, const void* src, uint32 n);
#endif
