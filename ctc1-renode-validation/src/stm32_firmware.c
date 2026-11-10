/* UART/NVIC/SysTick bench firmware. No inserted synthetic handler delays or RTOS. */
#include <stdint.h>
#include "cop1.h"
extern volatile uint32 input[4], output[10];
extern uint8 incoming[261], committed[256];
extern COP1_Clcw_t clcw;
extern void step(void);
#define REG(a) (*(volatile uint32_t *)(a))
#define UART 0x40004400U
#define RX_SIZE 2048U
#define REPLIES 32U
static volatile uint8_t rx_ring[RX_SIZE];
static volatile uint32_t rx_head, rx_tail, irq_count, rx_bytes, rx_drops, ticks;
static uint32_t protocol_errors, frame_count, max_owned, last_feedback, tx_records;
static uint32_t reply_head, reply_tail, reply_count, reply_peak, reply_errors, automatic;
static uint16_t reply_length[REPLIES], feedback_period = 100;
static uint8_t reply_data[REPLIES][256], tx_tm[280], message[300];
static uint32_t message_size, wanted;
static uint8_t tm_index;

#ifdef CTC_TIMING
#ifdef CTC_BOARD
#define CORE_HZ 16000000U /* STM32F407 hardware-reset HSI and undivided buses */
#else
#define CORE_HZ 72000000U /* Renode profile only */
#endif
#define DWT_CTRL 0xE0001000U
#define DWT_CYCCNT 0xE0001004U
#define DEMCR 0xE000EDFCU
enum { FARM_SAMPLE, COMMIT_SAMPLE, TM_SAMPLE, PHASES };
static uint32_t timing_ready;
static volatile uint32_t uart_overruns, uart_errors, rx_ring_peak;
static uint32_t timing_calls[PHASES], timing_max[PHASES];

static void init_timing(void) {
    REG(DEMCR) |= 1U << 24;
    if (REG(DWT_CTRL) & (1U << 25)) return;
    REG(DWT_CYCCNT) = 0;
    REG(DWT_CTRL) |= 1U;
    uint32_t before = REG(DWT_CYCCNT);
    for (unsigned i = 0; i < 16; ++i) {
        if (REG(DWT_CYCCNT) != before) {
            timing_ready = 1;
            break;
        }
    }
}

static uint32_t timing_start(void) {
    return timing_ready ? REG(DWT_CYCCNT) : 0;
}

static void timing_end(unsigned phase, uint32_t before) {
    uint32_t elapsed = timing_ready ? REG(DWT_CYCCNT) - before : 0;
    ++timing_calls[phase];
    if (elapsed > timing_max[phase]) timing_max[phase] = elapsed;
}

static void timed_step(unsigned phase) {
    uint32_t before = timing_start();
    step();
    timing_end(phase, before);
}
#else
#define CORE_HZ 72000000U
#define timed_step(phase) step()
#endif


void SysTick_Handler(void) { ticks++; }
void USART2_IRQHandler(void) {
    irq_count++;
    for (;;) {
        uint32_t sr = REG(UART);
#ifdef CTC_TIMING
        /* Reading SR then DR clears the STM32F4 receive error flags. */
        if (!(sr & ((1U << 5) | 0x0fU))) break;
#else
        if (!(sr & (1U << 5))) break;
#endif
        uint8_t value = (uint8_t)REG(UART + 4);
#ifdef CTC_TIMING
        if (sr & (1U << 3)) ++uart_overruns;
        if (sr & 7U) ++uart_errors;
        if (!(sr & (1U << 5))) continue;
#endif
        rx_bytes++;
#ifdef CTC_TIMING
        if (sr & 7U) continue;
#endif
        uint32_t next = (rx_head + 1) % RX_SIZE;
        if (next == rx_tail) rx_drops++;
        else {
            rx_ring[rx_head] = value;
            rx_head = next;
#ifdef CTC_TIMING
            uint32_t used = (next + RX_SIZE - rx_tail) % RX_SIZE;
            if (used > rx_ring_peak) rx_ring_peak = used;
#endif
        }
    }
}
static uint16_t crc_byte(uint16_t crc, uint8_t value) {
    crc ^= (uint16_t)value << 8;
    for (uint32_t i = 0; i < 8; i++) crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    return crc;
}
static void tx(uint8_t value) {
    while (!(REG(UART) & (1U << 7))) { }
    REG(UART + 4) = value;
}
static void record(uint8_t kind, uint8_t seq, const uint8_t *data, uint32_t length) {
    uint8_t header[4] = {kind, seq, (uint8_t)(length >> 8), (uint8_t)length};
    uint16_t crc = 0xffff;
    tx(0x5a); tx(0xa5);
    for (uint32_t i = 0; i < 4; i++) { tx(header[i]); crc = crc_byte(crc, header[i]); }
    for (uint32_t i = 0; i < length; i++) { tx(data[i]); crc = crc_byte(crc, data[i]); }
    tx((uint8_t)(crc >> 8)); tx((uint8_t)crc); tx_records++;
}
#ifdef CTC_TIMING
static void timing_record(uint8_t seq) {
    uint32_t data[12] = {1, CORE_HZ, timing_ready, uart_overruns, uart_errors, rx_ring_peak};
    for (unsigned i = 0; i < PHASES; ++i) {
        data[6 + 2 * i] = timing_calls[i];
        data[7 + 2 * i] = timing_max[i];
    }
    record(0x84, seq, (const uint8_t *)data, sizeof(data));
}
#endif

static void status(uint8_t seq) {
    uint32_t data[24];
    input[0] = 3; step();
    for (uint32_t i = 0; i < 10; i++) data[i] = output[i];
    data[10] = ticks; data[11] = irq_count; data[12] = rx_bytes; data[13] = rx_drops;
    data[14] = protocol_errors; data[15] = frame_count; data[16] = max_owned;
    data[17] = reply_peak; data[18] = reply_errors; data[19] = tx_records;
    data[20] = automatic; data[21] = feedback_period;
    data[22] = (uint32_t)REG(UART + 12); data[23] = (uint32_t)REG(0xE000E010);
    record(0x80, seq, (uint8_t *)data, sizeof(data));
}
static void enqueue_committed(void) {
    uint32_t n = output[6], offset = 0;
    if (!n) return;
    record(0x81, 0, committed, n);
    while (offset < n) {
        uint32_t size = 7U + ((uint32_t)committed[offset + 4] << 8) + committed[offset + 5];
        if (reply_count >= REPLIES || size < 14 || size > 256 || size > n - offset) { reply_errors++; return; }
        for (uint32_t i = 0; i < size; i++) reply_data[reply_tail][i] = committed[offset + i];
        reply_data[reply_tail][0] &= 0xef;
        reply_length[reply_tail] = (uint16_t)size;
        reply_tail = (reply_tail + 1) % REPLIES; reply_count++;
        if (reply_count > reply_peak) reply_peak = reply_count;
        offset += size;
    }
}
static void emit_tm(void) {
#ifdef CTC_TIMING
    uint32_t before = timing_start();
#endif
    for (uint32_t i = 0; i < 280; i++) tx_tm[i] = 0;
    tx_tm[0] = 2; tx_tm[1] = 0xa3; tx_tm[2] = tm_index; tx_tm[3] = tm_index++;
    tx_tm[4] = 0x18; tx_tm[5] = 0;
    uint32_t used = 0;
    while (reply_count && used + reply_length[reply_head] <= 261) {
        uint32_t length = reply_length[reply_head];
        for (uint32_t i = 0; i < length; i++) tx_tm[6 + used + i] = reply_data[reply_head][i];
        used += length; reply_head = (reply_head + 1) % REPLIES; reply_count--;
    }
    uint32_t idle = 268 - used;
    tx_tm[6 + used] = 7; tx_tm[7 + used] = 0xff;
    tx_tm[8 + used] = 0xc0;
    tx_tm[10 + used] = (uint8_t)((idle - 7) >> 8); tx_tm[11 + used] = (uint8_t)(idle - 7);
    uint8_t *c = (uint8_t *)&clcw;
    for (uint32_t i = 0; i < 4; i++) tx_tm[274 + i] = c[i];
    uint16_t crc = 0xffff;
    for (uint32_t i = 0; i < 278; i++) crc = crc_byte(crc, tx_tm[i]);
    tx_tm[278] = (uint8_t)(crc >> 8); tx_tm[279] = (uint8_t)crc;
    record(0x82, 0, tx_tm, 280);
#ifdef CTC_TIMING
    timing_end(TM_SAMPLE, before);
#endif
}
static void dispatch(void) {
    uint32_t n = ((uint32_t)message[4] << 8) | message[5];
    uint16_t crc = 0xffff;
    for (uint32_t i = 2; i < 6 + n; i++) crc = crc_byte(crc, message[i]);
    if (crc != (uint16_t)(((uint16_t)message[6 + n] << 8) | message[7 + n])) { protocol_errors++; return; }
    uint8_t op = message[2], seq = message[3];
    if (op == 0 && n == 5) {
        input[0] = 0; input[2] = message[7]; input[3] = message[6]; step();
        automatic = message[8]; feedback_period = ((uint16_t)message[9] << 8) | message[10];
        if (!feedback_period) feedback_period = 100;
        reply_head = reply_tail = reply_count = reply_peak = reply_errors = 0;
        frame_count = max_owned = 0; tm_index = 0; last_feedback = ticks;
#ifdef CTC_TIMING
        for (unsigned i = 0; i < PHASES; ++i) timing_calls[i] = timing_max[i] = 0;
#endif
    } else if (op == 1 && n >= 19 && n <= 261) {
        for (uint32_t i = 0; i < n; i++) incoming[i] = message[6 + i];
        input[0] = 1; input[1] = n; timed_step(FARM_SAMPLE); frame_count++;
        if (output[3] > max_owned) max_owned = output[3];
        record(0x83, seq, (const uint8_t *)output, 40);
    } else if (op == 2 && !n) { input[0] = 2; timed_step(COMMIT_SAMPLE); enqueue_committed(); }
    else if (op == 3 && !n) { }
    else if (op == 4 && !n) { emit_tm(); }
#ifdef CTC_TIMING
    else if (op == 5 && !n) { timing_record(seq); }
#endif
    else { protocol_errors++; }
    status(seq);
}
static void parse_rx(void) {
    while (rx_tail != rx_head) {
        uint8_t value = rx_ring[rx_tail]; rx_tail = (rx_tail + 1) % RX_SIZE;
        if (message_size == 0 && value != 0xa5) continue;
        if (message_size == 1 && value != 0x5a) { message_size = value == 0xa5 ? 1 : 0; continue; }
        message[message_size++] = value;
        if (message_size == 6) {
            wanted = 8 + ((uint32_t)message[4] << 8) + message[5];
            if (wanted > sizeof(message)) { protocol_errors++; message_size = 0; }
        }
        if (message_size >= 6 && message_size == wanted) { dispatch(); message_size = 0; }
    }
}
void firmware_main(void) {
#ifdef CTC_BOARD
    /* Require reset-clock configuration instead of assuming a debugger left it intact. */
    if (REG(0x40023808) & 0x1cfcU) for (;;) __asm volatile("wfi");
#endif
#ifdef CTC_TIMING
    init_timing();
#endif
    REG(0x40023830) |= 1U;              /* GPIOA clock */
    REG(0x40023840) |= 1U << 17;        /* USART2 clock */
    REG(0x40020000) = (REG(0x40020000) & ~0xf0U) | 0xa0U; /* PA2/PA3 AF */
    REG(0x40020020) = (REG(0x40020020) & ~0xff00U) | 0x7700U;
    REG(UART + 8) = 0x8bU;             /* 115200 at nominal 16 MHz; model ingress is paced by host */
    REG(UART + 12) = (1U << 13) | (1U << 5) | (1U << 3) | (1U << 2);
    REG(0xE000E104) = 1U << 6;         /* NVIC external IRQ 38 */
    *(volatile uint8_t *)0xE000E426 = 0x40;
    REG(0xE000E014) = CORE_HZ / 1000U - 1U; /* 1 ms at the selected nominal clock */
    REG(0xE000E018) = 0; REG(0xE000E010) = 7;
    input[0] = 0; input[2] = 3; input[3] = 1; step();
    status(0xff);
    for (;;) {
        parse_rx();
        if (automatic && output[3]) { input[0] = 2; timed_step(COMMIT_SAMPLE); enqueue_committed(); }
        uint32_t queued = 0;
        for (uint32_t i = 0, index = reply_head; i < reply_count; i++, index = (index + 1) % REPLIES) queued += reply_length[index];
        if (automatic && (queued >= 261 || ticks - last_feedback >= feedback_period)) { emit_tm(); last_feedback = ticks; }
        __asm volatile("wfi");
    }
}
