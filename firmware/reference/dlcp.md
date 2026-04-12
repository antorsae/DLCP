Kattegat 8 9723 JP Groningen, The Netherlands +31 50 526 4993 sales@hypex.nl www.hypex.nl 

**DLCP** 

**==> picture [91 x 60] intentionally omitted <==**

## **Digital Loudspeaker Cross-over Platform Datasheet** 

## **Highlights** 

**==> picture [222 x 170] intentionally omitted <==**

**==> picture [232 x 58] intentionally omitted <==**

**==> picture [232 x 58] intentionally omitted <==**

**==> picture [232 x 58] intentionally omitted <==**

**==> picture [232 x 58] intentionally omitted <==**

## **Description** 

The “DLCP” is a complete hardware/firmware platform for digitally filtered (6 channels) and corrected active multiway loudspeakers. Digital response correction allows significant extra degrees of freedom in the acoustic design of a loudspeaker. Driver parameters can be selected for best efficiency and distortion instead of electrical damping, and the cabinet can now be fully optimized for radiation pattern. For further information, please read the manual (in progress). 

**==> picture [9 x 9] intentionally omitted <==**

- Fully user customized filtering Great audio performance Field updatable firmware Current-mode serial I/F USB audio 

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

- Compact: 110mm x110mm x30mm Low weight: 140gr. 

**==> picture [9 x 9] intentionally omitted <==**

## **Features** 

**==> picture [9 x 9] intentionally omitted <==**

- Compact design Personal Computer controlled Input sample rates up to 192kHz Analogue and digital inputs Digital balanced audio loop-through Low-jitter discrete clock oscillator Balanced audio in and out Six channel active filtering Fully user-configurable filters Firmware updateable by USB Separate Clock and Data Paths 

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

- Six user configurable analogue balanced outputs High-Level outputs permit direct interface with NC400 / buffered UcD™ ST and HG power amplifiers Analogue input gain trim 9 local regulators IIR filtering 96kHz processor sampling rate Stand-by mode 

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

- On board Molex Microfit output connectors 

**==> picture [9 x 9] intentionally omitted <==**

- Connector for external LED. 

**==> picture [9 x 9] intentionally omitted <==**

- Optional control board with IR receiver for IR remote control, LCD display and buttons 

**==> picture [9 x 9] intentionally omitted <==**

- Link communication (only with two or more modules and in combination with a controller) 

## **Applications** 

**==> picture [9 x 9] intentionally omitted <==**

High-end consumer audio Digital pre amplifier 

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

- Active speakers up to six-way Three-way stereo active system PA systems Studio monitors 

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [9 x 9] intentionally omitted <==**

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **DLCP** 

Contents 

|1|Block diagram .......................................................................................................................................... 3|
|---|---|
|2|Performance data .................................................................................................................................... 4|
|3|Recommended Operating Conditions ................................................................................................... 4|
|4|Connections ............................................................................................................................................. 5|
|5|Pin characteristics ................................................................................................................................... 9|
|6|Typical Performance Graphs ................................................................................................................ 11|
|7|Dimensions ............................................................................................................................................ 13|
|8|Revision History .................................................................................................................................... 14|



R3 

2 

**DLCP** 

**Datasheet R3** 

**==> picture [91 x 60] intentionally omitted <==**

## **1 Block diagram** 

**==> picture [480 x 253] intentionally omitted <==**

**----- Start of picture text -----**<br>
27Mhz<br>5V PSU<br>DANTE /AES board,<br>27MHz, 3,3VPSU<br>**----- End of picture text -----**<br>


```
Clocksignal für DLCP 3,3V oder 5V?
Clocksignal für DANTE 3,3V oder 5V?
```

```
Weiterer Übertager an Neutrino Clock nötig/möglich?
```

R3 

3 

**DLCP** 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **2 Performance data** 

## **MBW=20kHz (20Hz-20Khz), unweighted, all filters set to unity, gain adjust 0dB unless otherwise noted** 

|**otherwise noted**|||||||
|---|---|---|---|---|---|---|
|**Item**|**Symbol**|**Min**|**Typ**|**Max**|**Unit**|**Notes**|
|Input level<br>1)|VIN||24.25||dBu|Gain adjust 0dB|
||||17.95|||Gain adjust+6dB|
||||12|||Gain adjust+12dB|
||||9|||Gain adjust+15dB|
|Output level|VOUT||2.59||V|0 dBFS(differential)|
|Signal/Noise ratio|SNR||113||dB|Digital in|
||||110||dB|Analogue in|
|Total harmonic distortion + noise|THD+N||-102||dB|Digital in, -1dBFS|
||||-102||dB|Analogue in,<br>-1dBFS|
|Output noise digital|UN||5,8||uV|20Hz-20kHz|
|Output noise analogue|||7,4||||
|DM Input Impedance|ZIN,DM||44||kΩ|Differential mode|
|CM Input Impedance|ZIN,CM||2.2||MΩ|Common mode|
|Output Impedance|<br>ZOUT||100||Ω||
|Frequency Response<br>(relative to 1kHz)||0||35|kHz|+/- 0.1dB|
|||-0.2||0.1|dB|DC-0.45fs or 42kHz<br>(whichever is<br>lowest)|
|DSP sampling rate|Fs||93.75||kHz||
|ADC sampling rate|Fs||93.75||kHz||
|Supported digital sampling rates|Fs|32, 44.1, 48, 88.2, 96,<br>192|||kHz|All input rates<br>converted to<br>93.75kHz|
|Delay per channel||0|0|10|mS|Set in software|
|CM Rejection Ratio|CMRR||70||dB|All frequencies<br>(gain adjust+15)|
|Channel separation|||>108||dB|Left/Right and<br>interchannel<br>seperation|
|Analogue latency|||750||uS||
|Digital latency|||1.85||ms|96kHz input<br>sample rate|
|StandbyCurrent|ISTBY||30||mA||



**Note 1:** See J5/J8 in Connections. 

## **3 Recommended Operating Conditions** 

|**Item **|**Symbol **|**Min**|**Typ**|**Max **|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|Supply voltage||15.5<br>1)|18|26<br>2)|Vdc|Positive and<br>negative<br>supply<br>voltage|



**Note 1:** Unit shuts down when the positive rail drops below 15V. 

**Note 2:** Especially on high supply voltages; make sure there’s enough airflow to cool the regulators. 

R3 

4 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **DLCP** 

## **4 Connections** 

**==> picture [481 x 166] intentionally omitted <==**

**==> picture [481 x 166] intentionally omitted <==**

**==> picture [481 x 167] intentionally omitted <==**

**----- Start of picture text -----**<br>
- +<br>**----- End of picture text -----**<br>


R3 

5 

**DLCP** 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## Overview of the connectors on the DLCP 

|Name|Function|
|---|---|
|**J1**|Analogue audio output header (contains all audio outputs from J10-J15)|
|**J2**|Analogue/Digital audio in and digital output header|
|**J3**|I/O connector (USB, Relay, Control)|
|**J4**|DLCP SMPS power supply connector(Do not use when a Hypex SMPS module is connected<br>with J16)|
|**J5**|Gain adjust header analogue left input|
|**J8**|Gain adjust header analogue right input|
|**J17**|Standby supply connector|
|**J10**|Analogue audio output ch1|
|**J11**|Analogue audio output ch2|
|**J12**|Analogue audio output ch3|
|**J13**|Analogue audio output ch4|
|**J14**|Analogue audio output ch5|
|**J15**|Analogue audio output ch6|
|**J16**|Power Supply connector Hypex SMPS(Do not use when J4 is connected to a supply)|
|**J7**|LED connector|
|**J6**|Microcontroller & DSP programmer connector, not used by user|
|**JP5**|Jumpers for programming or normal operation, not used by user|



## **4.1 J1: Analogue audio out** 

## Connector type: 2.54mm pitch dual row 10 pin box header 

|||||
|---|---|---|---|
|**Pin**|**Type **|**Function**||
|1|Output|Ch1 positive out||
|2|Output|Ch1 negative out||
|3|Output|Ch2 positive out||
|4|Output|Ch2 negative out||
|5|-|GND||
|6|-|GND||
|7|Output|Ch3 positive out||
|8|Output|Ch3 negative out||
|9|Output|Ch4 positive out||
|10|Output|Ch4 negative out||
|11|-|GND||
|12|-|GND||
|13|Output|Ch5 positive out||
|14|Output|Ch5 negative out||
|15|Output|Ch6 positive out||
|16|Output|Ch|~~6 positive~~out|
|17|Output|Amp_enable||
|18|-|GND||
|19||N.C.||
|20||N.C.||



R3 

6 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **DLCP** 

## **4.2 J2: Analogue/digital audio I/O** 

## Connector type: 2.54mm pitch dual row 7 pin box header 

|**Pin**|**Type **|**Function**|
|---|---|---|
|1|Input|Analogue left positive in|
|2|Input|Analogue left negative in|
|3|Input|Analogue right positive in|
|4|Input|Analogue right negative in|
|5|-|GND|
|6|-|GND|
|7|Input|S/PDIF in|
|8|Output|S/PDIF out|
|9|Input|AES positive in|
|10|Input|AES negative in|
|11|Output|AES positive out|
|12|Output|AES negative out|
|13|Input|Optical in (S/PDIF interface)|
|14|-|GND|



Please place this filter on your analogue inputs if you don’t use the optional DLCP input board; 

**==> picture [310 x 135] intentionally omitted <==**

## **4.3 J3: I/O USB,midi,relay** 

Connector type: 2.54mm pitch dual row 8 pin box header 

|**Pin**|**Type **|**Function**|
|---|---|---|
|1|Input|Midi in positive|
|2|Input|Midi in negative|
|3|Output|Midi positive out|
|4|Output|Midi negative out|
|5|In/output|USB data positive|
|6|In/output|USB data negative|
|7|Input|USB VCC|
|8|-|GND|
|9|Output|Relay supply voltage|
|10|Output|Relay 1 control|
|11|Output|Relay 2 control|
|12|Output|Relay 3 control|
|13|-|GND|
|14|Output|Controller board supply voltage (+5V)|
|15||For future use|
|16||N.C.|



R3 

7 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **DLCP** 

## **4.4 J7: External LED** 

Connector type: 2.54mm pitch 2 pin header 

|Pin|Type|Function|
|---|---|---|
|1|Output|Led output (anode)|
|2|-|GND (cathode)|



See section External LED output 

## **4.5 J10-J15: Analogue audio out (ch1-ch6)** 

Connector type: 2x2 pin Molex® Microfit® header type 43045-0412 (see www.molex.com), mates - with 43025 0400 cable part. 

|Pin|Type|Function|||
|---|---|---|---|---|
|1|Output|Ch positive out|||
|2|Output|Ch negative out|||
|3|Output|Amplifier enable|11k an 9V bringbei HIGH ca 3,3V||
|4|-|GND|10k an 9V bring bei HIGH ca 3, V||



The audio output is differential. This means that ground is not part of the audio signal. When connecting an unbalanced amplifier, treat pins 1 and 2 as a floating output with pin 2 being the “audio ground” of the amplifier. Pin 4 may be used to attach the shield of a shielded twisted pair cable, but the “audio ground” connection of an unbalanced amplifier should never connect here. 

## **4.6 J16: Hypex SMPS power supply** 

Connector type JST (www.jst.com) JST-B7B-EHA, mates with JST-EHR-7 cable part. This connector should not be used when J4 is connected to another power supply. 

|Pin|Type|Function|||
|---|---|---|---|---|
|1|Output|Supply standby (Electrically connected to pin 1 of J4)<br>high=stby voltage|||
|2<br>3|Output<br>Input|Amplifier standby (Electrically connected to pin 2 of J4)<br>Positive input voltage (Electrically connected to pin 3 and 4 of J4)<br>high=stby voltage,  low=on mit ca 2,5sec|delay!||
|4||N.C.|||
|5|-|GND|||
|6||N.C.|||
|7|Input|Negative input voltage (Electrically connected to pin 7 and 8 of J4)|||



## **4.7 J4: Power Supply** 

|**4.7** **J4: Power Supply**|**4.7** **J4: Power Supply**|**4.7** **J4: Power Supply**|**4.7** **J4: Power Supply**|**4.7** **J4: Power Supply**||||||
|---|---|---|---|---|---|---|---|---|---|
|Connector type: 2.54mm pitch dual row 5 pin box header||||||||||
|This connector should not be used when J16 is connected to a Hypex SMPS power supply.||||||||||
|Pin||Type||Function||||||
|1||Output||Supply standby (Electrically connected to pin 1 of J16)||||||
|2|Input<br>output?!|||Amplifier standby (Electrically connected to pin 2 of J16)||||||
|3||Input||Positive input voltage (Electrically connected to pin 3 of J16)||||||
|4||Input||Positive input voltage (Electrically connected to pin 3 of J16)||||||
|5||-||GND||||||
|6||Input||Standby voltage (Electrically connected to pin 1 of J17)||||||
|||||||||||
|7||Input||Negative input voltage (Electrically connected to pin 7 of J16)||||||
|8||Input||Negative input voltage (Electrically connected to pin 7 of J16)||||||
|9||Input||Amplifier positive supply voltage measurement||||||
|10||Input||Amplifier negative supply voltage measurement||||||



## **4.8 J17: Standby** 

|**4.8** **J17: Standby**|**4.8** **J17: Standby**|**4.8** **J17: Standby**||
|---|---|---|---|
|Connector type JST (www.jst.com) JST-B2P-VH, mates with JST-VHR-2N cable part.||||
|Pin|Type|Function||
|1|Input|Standby voltage (Electrically connected to pin 6 of J4)||



8 

R3 

**DLCP** 

**Datasheet R3** 

**==> picture [91 x 60] intentionally omitted <==**

- 2 GND 

## **5 Pin characteristics** 

## **5.1 Amp_enable output** 

This pin is controlled by the microcontroller (open collector). This pin is left floating, when the amplifier should be in standby mode/should be muted, in normal operation it’s connected to ground. 

## **5.2 Relay 1,2,3 control output** 

These pins control the relays on the optional DLCP Inputboard. These are open collector outputs. 

||||
|---|---|---|
|AnalogueInputselect|Relay controloutputs|High/Low|
|Analogue 1|1|High (Open collector)|
||2|High (Open collector)|
||3|High (Open collector)|
|Analogue 2|1|Low (Pulled to ground)|
||2|High (Open collector)|
||3|High (Open collector)|
|Analogue 3|1|High (Open collector)|
||2|High (Open collector)|
||3|Low (Pulled to ground)|
|Analogue 4|1|High (Open collector)|
||2|Low (Pulled to ground)|
||3|Low (Pulled to ground)|



## **5.3 Amplifier standby** 

This open collector output pin is controlled by the microcontroller, and is by default pulled up to the standby supply voltage. It’s pulled to ground when the amplifiers should be enabled. For more information see datasheet of the Hypex SMPS XXX. 

## **5.4 Supply standby output** 

This pin is controlled by the microcontroller, and is high when the DLCP is in standby mode. When connected to a Hypex SMPS XXX, see datasheet of the connected SMPS for more information. In order to use this function a standby supply voltage must be present. 

## **5.5 Amplifier positive supply voltage measurement input** 

This pin can be used to measure the positive amplifier supply voltage, for a limiter, but is not yet implemented in software. 

|**Item**|**Type**|**Min**|**Typ**|**Max**|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|Positive Voltage on J4:9|Input|TBD|TBD|TBD|Vdc||



## **5.6 Amplifier negative supply voltage measurement input** 

This pin can be used to measure the negative amplifier supply voltage, for a limiter, but is not yet implemented in software. 

|implemented in software.|||||||
|---|---|---|---|---|---|---|
||||||||
|**Item **|**Type**|**Min**|**Typ**|**Max **|**Unit**|**Notes**|
|Negative Voltage on J4:10|Input|TBD|TBD|TBD|Vdc||



## **5.7 Relay supply voltage output** 

Supply voltage for relays on optional DLCP Input PCB. 

|**Item **|**Type**|**Min**|**Typ**|**Max **|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|Voltage on J3:9|Output||5||Vdc|Max. current=110 mA.|



9 

R3 

**DLCP** 

**Datasheet R3** 

**==> picture [91 x 60] intentionally omitted <==**

## **5.8 External LED output** 

**==> picture [114 x 150] intentionally omitted <==**

A LED connected to J7 will light up when the DLCP is turned on, and flashes a few times when the supply voltage drops below 15Vdc. 

## **5.9 Controller board supply voltage output** 

This supply pin is used for the control board. 

|**Item **|**Type**|**Min**|**Typ**|**Max **|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|Voltage on J3:14|Output||5||Vdc||



## **5.10 Positive input voltage** 

|**Item**|**Type**|**Min**|**Typ**|**Max**|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|DC voltage on J4:3 and 4<br>/J16:3|Input|15.5|18|26|Vdc||
|Current<br>1)|Input|300||390|mA||
|Current<br>1)|Input|380||490|mA|With optional Inputboard<br>and Control.|



**Note 1:** Maximum current value is drawn at min. input supply voltage, min. current value is drawn at max. input supply voltage (because of the DC-DC converters). 

## **5.11 Negative input voltage** 

|**Item **|**Type**|**Min**|**Typ**|**Max **|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|DC voltage on J4:7 and 8<br>/J16:7|Input|15.5|18|26|Vdc||
|Current|Input|180||180|mA||



## **5.12 Standby Input** 

When you want to use the standby mode of the DLCP, you have to apply an external DC voltage (standby supply) on J17 / J4:6. 

|**Item**|**Type**|**Min**|**Typ**|**Max**|**Unit**|**Notes**|
|---|---|---|---|---|---|---|
|DC voltage on J17:1/J4:6|input|6.5|8|12|Vdc||
|Current|Input||30|40|mA||



## **5.13 Chassis grounding** 

All four mounting holes are connected to ground with a 100nF capacitor. Connect them all to chassis with a metal spacer for optimum EMI performance. 

10 

R3 

**DLCP** 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **6 Typical Performance Graphs** 

## **6.1 Frequency response (Analogue)** 

+1 +0.9 +0.8 +0.7 +0.6 +0.5 +0.4 +0.3 +0.2 +0.1 +0 -0.1 -0.2 -0.3 -0.4 -0.5 -0.6 -0.7 -0.8 -0.9 -1 20 50 100 200 500 1k 2k 5k 10k 20k 50k Hz 

## **6.2 THD+N vs. input voltage (Analogue, 1Khz)** 

**==> picture [482 x 203] intentionally omitted <==**

**----- Start of picture text -----**<br>
-60<br>-62.5<br>-65<br>-67.5<br>-70<br>-72.5<br>-75<br>-77.5<br>-80<br>-82.5<br>-85<br>d -87.5<br>B<br>r -90<br>A -92.5<br>-95<br>-97.5<br>-100<br>-102.5<br>-105<br>-107.5<br>-110<br>-112.5<br>-115<br>-117.5<br>-120<br>-30 -28 -26 -24 -22 -20 -18 -16 -14 -12 -10 -8 -6 -4 -2 -0<br>dBr<br>**----- End of picture text -----**<br>


R3 

11 

**==> picture [91 x 60] intentionally omitted <==**

## **Datasheet R3** 

## **DLCP** 

## **6.3 THD+N vs. Frequency (Analogue in, -1 dBFS)** 

**==> picture [482 x 203] intentionally omitted <==**

**----- Start of picture text -----**<br>
-60<br>-62.5<br>-65<br>-67.5<br>-70<br>-72.5<br>-75<br>-77.5<br>-80<br>-82.5<br>-85<br>d -87.5<br>B<br>r -90<br>A -92.5<br>-95<br>-97.5<br>-100<br>-102.5<br>-105<br>-107.5<br>-110<br>-112.5<br>-115<br>-117.5<br>-120<br>20 50 100 200 500 1k 2k 5k 10k 20k<br>Hz<br>**----- End of picture text -----**<br>


## **6.4 FFT (Analogue in, -20dBFS, 5kHz )** 

**==> picture [484 x 203] intentionally omitted <==**

**----- Start of picture text -----**<br>
+0<br>-10<br>-20<br>-30<br>-40<br>-50<br>-60<br>d -70<br>B<br>r -80<br>A -90<br>-100<br>-110<br>-120<br>-130<br>-140<br>-150<br>0 1k 2k 3k 4k 5k 6k 7k 8k 9k 10k 11k 12k 13k 14k 15k 16k 17k 18k 19k 20k 21k 22k 23k 24k 25k<br>Hz<br>**----- End of picture text -----**<br>


R3 

12 

**DLCP** 

**Datasheet R3** 

**==> picture [91 x 60] intentionally omitted <==**

## **7 Dimensions** 

Top view 

**==> picture [357 x 90] intentionally omitted <==**

**==> picture [357 x 89] intentionally omitted <==**

**==> picture [357 x 89] intentionally omitted <==**

**==> picture [357 x 88] intentionally omitted <==**

Side view 

**==> picture [481 x 123] intentionally omitted <==**

R3 

13 

**Datasheet R3** 

**==> picture [91 x 60] intentionally omitted <==**

## **DLCP** 

**DISCLAIMER: This product is designed for use in sound reproduction equipment in conjunction with Hypex amplifier modules. No representations are made as to fitness for use in other applications. Except where noted otherwise any  specifications given pertain to this subassembly only. Responsibility for verifying the performance, safety, reliability and compliance with legal standards of end products using this subassembly falls to the manufacturer of said end product.** 

**LIFE SUPPORT POLICY: Use of Hypex products in life support equipment or equipment whose failure can reasonably be expected to result in injury or death is not permitted except by explicit written consent from Hypex Electronics BV.** 

## **Warranty** 

The work carries warranty out for all provable material and production defects for the duration of 24 months starting from sales. All damage, which is caused by wrong or inappropriate operation, is excluded from the warranty. 

## **8 Revision History** 

The following table shows the revision history for this document. 

|**Document**<br>**Revision **|**PCB**<br>**Version**|**Description**|**Date**|
|---|---|---|---|
|R1|DLCP V1|Initial Draft.|23.11.2010|
|R2|DLCP V3|Updated because of new hardware version|18.12.2012|
|R3|DLCP V4|Typos changed, pinout picture updated|10.12.2014|



R3 

14 

