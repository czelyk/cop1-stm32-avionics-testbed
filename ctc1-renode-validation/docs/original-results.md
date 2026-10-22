# CTC1 — STM32/Renode deney raporu

14 Ekim 2026. **İşlevsel uçtan uca test başarılı; gerçek STM32 zamanlama doğrulaması yapılmadı. IAC kararı CONDITIONAL olarak kalıyor.**

## Gerçekte çalıştırılan yol

Sabitlenmiş yerel Yamcs FOP → varsayılan ileri-hat seri süresi → Renode STM32F4 USART2 → gerçek Cortex-M4 firmware, NVIC RX kesmesi ve SysTick → değiştirilmemiş NASA FARM → sahipliği korunan FDU tamponları → echo komut işleme/boşaltma → STM32 firmware'inde TM paketleme, CRC ve CLCW → varsayılan dönüş-hatı seri süresi → yerel FOP ve bağımsız yanıt kontrolü.

STM32F4 Discovery tabanlı modelde 1 MiB flash/128 KiB SRAM ile sınırlandırılmış bir deney profili kullanıldı. ELF gerçek ARM talimatlarıyla çalışır. Host tarafı FARM sonucunu veya yanıtı hesaplayıp hedef yerine koymaz. Ham UART kayıtları, firmware çıktıları ve komut kimlikleri saklandı. RF, DMA, RTOS veya tam cFS portu yoktur.

## Doğrulanmış sonuçlar

- Ana matris: **16 koşul, 384/384 tam ve tekil komut işleme/yanıt**. 1/2/4/8 tampon; 100/1000 ms geri bildirim; varsayılan 4/256 kbit/s ileri-hat hızları; yeni talep tohumu 67.
- Ayrı taze keşif kampanyası: **9 koşul, 216/216 tam ve tekil komut işleme/yanıt**. UART baud ayarı 500000 olarak monitörden doğrulandı; yeni tohumlar 81/83/89; 50/100 MIPS eşleştirmeleri; bir ilk-çerçeve kaybı kontrolü.
- Toplam iki kampanya: **25 koşul, 600 kaynak = 600 handler commit = 600 doğru yanıt**; eksik/yinelenen işleme yok. Her koşulda 255→0 sıra dönüşü görüldü. Kaybolan çerçeve gerçek FOP tarafından yeniden gönderildi ve 24 komut doğru tamamlandı.
- Manuel tampon sahipliği kontrolleri: dört kapasitede 19 tekil işleme; Wait, boşaltma/E10, tekrar kabul, yinelenen çerçeve reddi, yanlış uzunluk ve bellek guard kontrolleri geçti. Bunlar bilerek tutulan tamponlarla işlevsel kontrollerdir, nominal iş yükü bulgusu değildir.
- STM32'nin ürettiği **425 TM çerçevesi** ayrı sabitlenmiş yerel Yamcs çözücüsüyle denetlendi: CRC, OCF/CLCW, veri sınırları ve ilk paket konumu doğru. Bozulmuş CRC kontrolü reddedildi.
- Yazılım RX ring, protokol çözümleme ve yanıt kuyruğu hata sayaçları sıfır kaldı. Bu sayaçlar fiziksel UART overrun kanıtı değildir.

İki 24-komut pilotu ayrı tutuldu;600 toplamına eklenmedi. Ana ve keşif koşulları aynı firmware/model ailesini paylaşır;600 kayıt bağımsız istatistiksel tekrar değildir. Tahmin aralığı veya fiziksel WCET iddiası yoktur.

## Önemli model bulgusu ve sürüm sınırları

Renode'un sabitlenmiş [STM32_UART modeli](https://github.com/renode/renode-infrastructure/blob/066a7f13c052215632d469c995c89aea37c573b1/src/Emulator/Peripherals/Peripherals/UART/STM32_UART.cs) RX baytlarını baud hızına göre zamanlar; alınan veriyi dahili kuyruğa koyar, ORE'yi sürekli false ve TXE'yi sürekli true kabul eder. Gerçek alıcı overrun'ı ve TX veri yazma sınırı bu modelle kanıtlanamaz. TX çıktısından dönüş hattı süresi ayrı bir varsayım olarak hesaplanır.

V1 UART giriş saat varsayımı 8 MHz ve firmware BRR139 ile 57553 baud'dur. Bu nedenle dış modelde 256 kbit/s seçilmiş olması, V1'de FARM'ın o hızla beslendiğini göstermez. Bu gerçek kaynak incelemesinden sonra rapora eklendi; V1 verisi/charter'ı değiştirilmedi. Taze V3 kampanyası, aynı firmware'de BRR16'yı açıkça ayarlayıp 500000 baud okumasını doğrular.8N1 karakter taşıması, deney zarfı dahil bu ileri-hat referansı için yeterli model kapasitesi sağlar. Fiziksel kart veya saat ağacı ölçümü değildir.

Renode [zaman modeli](https://renode.readthedocs.io/en/latest/advanced/time_framework.html) CPU hızını MIPS ve zamanı sanal süreyle tanımlar.100 MIPS, gerçek STM32'nin 100 MHz'de veya belirli çevrim maliyetlerinde çalıştığı anlamına gelmez. SysTick bu profilde 72 MHz saat varsayımı ve 72000 reload ile 1 ms üretir. CPU MIPS ve çevre birimi saatleri ayrı model parametreleridir; fiziksel RCC/PLL/saat ağacı doğrulanmadı.

## Zamanlama ve bellek sınırı

CSV'deki gecikmeler, en fazla 5 ms aralıklarla toplanan emülasyon çıktısı ve varsayılan seri-hat süresidir; gerçek komut tamamlanma zamanı veya fiziksel hizmet kalibrasyonu değildir. En büyük bu tür kaynak→yanıt gecikmesi 5.335049 sanal saniyedir. Kayıt/CRC tanılama kodunun yükü firmware içinde vardır; observer overhead bağımsız kalibre edilmedi. Handler'a yapay bekleme veya ağır CPU yükü eklenmedi.

Gerçek derleme kesimleri: vector 392, text 5100, data 16, BSS13752 bayt. Linker 8 KiB stack alanı ayırır; çalışma sırasındaki stack high-water ölçülmedi. Tüm koşullarda sekiz-slot image bulunur, yalnız aktif kapasite seçilir; bu koşullar fiziksel RAM tasarrufu karşılaştırması değildir. Modelin gizli host/peripheral kuyruk belleği MCU RAM hesabına dahil değildir.

## Saklanan hatalar ve düzeltmeler

İlk pilotta bir RX-kesme delta özet alanı yanlış hesaplandı; gerçek 24/24 kimlik sonucu değişmedi. İlk kaynak/çıktı korundu, `pre_freeze` ve `pilot` altında bulunur; bu delta alanı kullanılmaz. Düzeltme ana matris dondurulmadan önce yapıldı ve ayrı taze pilotta kontrol edildi.

V2 hızlı-UART hazırlığı monitörden ondalık 500000 bekledi; Renode aynı sayıyı0x0007A120 gösterince assertion durdu. Henüz hedef koşulu çalışmamıştı. V2 kaynak/spec/log ve `exploratory_v2_failure.json` korundu. V3 doğru sayı gösterimini kabul eder; yeni tohumlarla ayrı spec dondurulup çalıştırılır. FARM veya firmware algoritması değiştirilmedi.

Decoder denetimindeki ilk assertion ham header pointer alanı 0'ı bekledi; yerel API mutlak frame byte konumu 6'yı döndürür. API beklentisi düzeltildi; ilk checker kaynağı/açıklaması `postprocessing_revisions` altında korundu. Firmware, çerçeve baytları, koşullar veya karar kriterleri değiştirilmedi.

## Bilimsel karar

Bu sonuç önceki Unicorn çalışmasının ötesinde STM32 çevre birimi, interrupt/vector başlangıcı, zamanlayıcı, firmware içi TM üretimi ve gerçek ground-peer bağlantısı için güçlü bir işlevsel entegrasyon kontrolüdür. Bir fiziksel kart pilotunun yazılım riskini azaltır.

Kaynak-kalibreli modelin gerçek kartta görülmemiş yükleri doğru tahmin ettiğini, yararlı kaynak seçimini veya özgün bir IAC katkısını göstermez. Önceki bilimsel karar değişmedi: **sınırlı fiziksel pilot için CONDITIONAL; mevcut ana araştırma iddiasını kurulmuş sonuç olarak sunmak için NO-GO.** Donanım olmadan işlevsel deneme ilerledi, fakat fiziksel hizmet/uncertainty, gerçek UART/DMA/RTOS davranışı ve yakın literatüre anlamlı fark halen eksik.

## Koşul tablosu

| Koşul | FDU slot | Geri bildirim ms | UART baud | Varsayılan MIPS | Doğru yanıt | Tepe FDU |
|---|---:|---:|---:|---:|---:|---:|
| r256000_n1_fb1000_s67 | 1 | 1000 | 57553 | 100 | 24/24 | 1 |
| r256000_n1_fb100_s67 | 1 | 100 | 57553 | 100 | 24/24 | 1 |
| r256000_n2_fb1000_s67 | 2 | 1000 | 57553 | 100 | 24/24 | 1 |
| r256000_n2_fb100_s67 | 2 | 100 | 57553 | 100 | 24/24 | 1 |
| r256000_n4_fb1000_s67 | 4 | 1000 | 57553 | 100 | 24/24 | 1 |
| r256000_n4_fb100_s67 | 4 | 100 | 57553 | 100 | 24/24 | 1 |
| r256000_n8_fb1000_s67 | 8 | 1000 | 57553 | 100 | 24/24 | 1 |
| r256000_n8_fb100_s67 | 8 | 100 | 57553 | 100 | 24/24 | 1 |
| r4000_n1_fb1000_s67 | 1 | 1000 | 57553 | 100 | 24/24 | 1 |
| r4000_n1_fb100_s67 | 1 | 100 | 57553 | 100 | 24/24 | 1 |
| r4000_n2_fb1000_s67 | 2 | 1000 | 57553 | 100 | 24/24 | 1 |
| r4000_n2_fb100_s67 | 2 | 100 | 57553 | 100 | 24/24 | 1 |
| r4000_n4_fb1000_s67 | 4 | 1000 | 57553 | 100 | 24/24 | 1 |
| r4000_n4_fb100_s67 | 4 | 100 | 57553 | 100 | 24/24 | 1 |
| r4000_n8_fb1000_s67 | 8 | 1000 | 57553 | 100 | 24/24 | 1 |
| r4000_n8_fb100_s67 | 8 | 100 | 57553 | 100 | 24/24 | 1 |
| v3_loss_r256000_n1_fb100_s89_m100 | 1 | 100 | 500000 | 100 | 24/24 | 1 |
| v3_r256000_n1_fb1000_s81_m100 | 1 | 1000 | 500000 | 100 | 24/24 | 1 |
| v3_r256000_n1_fb1000_s83_m100 | 1 | 1000 | 500000 | 100 | 24/24 | 1 |
| v3_r256000_n1_fb1000_s83_m50 | 1 | 1000 | 500000 | 50 | 24/24 | 1 |
| v3_r256000_n1_fb100_s83_m100 | 1 | 100 | 500000 | 100 | 24/24 | 1 |
| v3_r256000_n1_fb100_s83_m50 | 1 | 100 | 500000 | 50 | 24/24 | 1 |
| v3_r256000_n2_fb1000_s81_m100 | 2 | 1000 | 500000 | 100 | 24/24 | 1 |
| v3_r256000_n4_fb1000_s81_m100 | 4 | 1000 | 500000 | 100 | 24/24 | 1 |
| v3_r256000_n8_fb1000_s81_m100 | 8 | 1000 | 500000 | 100 | 24/24 | 1 |

`RENODE-VERIFIED-RESULTS.json`, `renode_case_results.csv`, `native_tm_verification.json`, ham per-event/byte kayıtları ve manifestler tüm sayıları denetlenebilir biçimde saklar. Eski CTC1 belgeleri, ham sonuçlar ve dondurulmuş dosyalar hash ile yeniden kontrol edildi; değişmedi.
