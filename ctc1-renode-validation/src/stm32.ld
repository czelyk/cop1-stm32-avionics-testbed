ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1024K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K }
_stack_top = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) } > FLASH
 .data : { _sdata = .; *(.data*) _edata = .; } > RAM AT > FLASH
 _sidata = LOADADDR(.data);
 .bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) _ebss = .; } > RAM
 . = ALIGN(8); _end = .;
 /DISCARD/ : { *(.comment*) *(.ARM.exidx*) *(.ARM.extab*) }
}
ASSERT(_end < _stack_top - 8192, "Insufficient reserved stack")
