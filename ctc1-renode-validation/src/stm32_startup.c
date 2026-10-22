#include <stdint.h>
extern uint32_t _stack_top, _sdata, _edata, _sidata, _sbss, _ebss;
extern void firmware_main(void);
void USART2_IRQHandler(void);
void SysTick_Handler(void);
static void Default_Handler(void) { for (;;) __asm volatile("wfi"); }
void boot(void) {
    uint32_t *source = &_sidata;
    for (uint32_t *p = &_sdata; p < &_edata; p++) *p = *source++;
    for (uint32_t *p = &_sbss; p < &_ebss; p++) *p = 0;
    *(volatile uint32_t *)0xE000ED08 = 0x08000000;
    firmware_main();
    Default_Handler();
}
__attribute__((naked, noreturn)) void Reset_Handler(void) {
    __asm volatile("ldr sp, =_stack_top\nbl boot\nb .");
}
__attribute__((used, section(".isr_vector")))
void (*const vectors[98])(void) = {
    [0] = (void (*)(void))(&_stack_top), [1] = Reset_Handler,
    [2] = Default_Handler, [3] = Default_Handler, [4] = Default_Handler,
    [5] = Default_Handler, [6] = Default_Handler, [11] = Default_Handler,
    [12] = Default_Handler, [14] = Default_Handler, [15] = SysTick_Handler,
    [16 + 38] = USART2_IRQHandler,
};
