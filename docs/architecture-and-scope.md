# Architecture and evidence boundary

The research path comprises a ground COP-1 FOP, telemetry/CLCW feedback, a NASA FARM-based receive core, finite FDU ownership, and a bounded command echo sink.

Two environments must not be conflated:

1. **ARM/Unicorn-based software integration:** NASA `cop1.c` / `tctf.c` run as ARM instructions with explicit cFE and memory adapters; Java Yamcs peer uses a virtual executor. Assigned virtual service durations are *not* measured microcontroller performance.
2. **STM32F4/Renode peripheral simulation:** Reported later work includes USART2 RX interrupts, NVIC, SysTick, real ARM firmware and generated TM/CLCW output. Its source is not in this package; a local importer is supplied. The Renode UART model and virtual clock do not establish physical UART overrun behavior or physical timing.

It is essential to distinguish transfer-frame acceptance from command-handler execution, FDU pool memory from **all** system buffers, and successful functional delivery from bounded worst-case timing.
