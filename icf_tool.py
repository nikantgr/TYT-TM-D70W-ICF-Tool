import csv
"""
ICF Tool - Bidirectional Converter for .icf Radio Files and CHIRP CSVs

Usage:
  python icf_tool.py decode <input.icf> [out_channels.csv] [out_settings.csv]
  python icf_tool.py encode <in_channels.csv> <in_settings.csv> <output.icf> [template.icf]

Commands:
  decode: Converts an .icf file into two CSVs (channels and settings).
  encode: Converts two CSVs back into an .icf file.
          If template.icf is provided, it will be used as a base.
          Otherwise, a default blank ICF will be generated.

Features:
  - Supports 200 channels with Names, Frequencies, Tones (CTCSS/DCS), Power, and Mode.
  - Supports detailed radio settings (Mic Gain, SQL Level, TOT, LED Mode, etc.).
  - Preserves binary structure and padding (spaces vs nulls).
"""
import sys
import os
import base64
import zlib

# Constants from Class1.cs
CON_ONE_ROW_DAT_CT = 32
FIEL_BEG_ROW = 3
CH_INF_ADDR = 0
CH_INF_NAME_ADDR = 8960
CON_ONE_CH_DAT_CT = 21
CON_ONE_CH_NAME_DAT_CT = 10
CON_SET_BEG_ADDR = 4448
CH_INF_BEG_ADDR = 4480  # Channel Status/Masks
CH_SKIP_BEG_ADDR = 4512 # Scan Skip Status
OPEN_RADIO_NAME_ADDR = 6592

# DTMF Settings
CON_DTMF_CH_ADDR = 4544
CON_DTMF_SET_ADDR = 4768
CON_ONE_DTMF_CH_DAT_CT = 13

# 2Tone Settings
CON_TONE2_CH_ADDR = 4864
CON_TONE2_RX_ADDR = 5056
CON_ONE_TONE2_CH_DAT_CT = 11

# 5Tone Settings
CON_TONE5_TX_ADDR = 5088
CON_TONE5_SET_ADDR = 5600
CON_TONE5_RX_ADDR = 5632
CON_ONE_TONE5_TX_DAT_CT = 32
CON_ONE_TONE5_RX_DAT_CT = 16

# GPS Settings
CON_GPS_CH_ADDR = 8576
CON_GPS_SET_ADDR = 8832
CON_ONE_GPS_CH_DAT_CT = 8

# FM Radio Settings from RadioSYS.cs
CON_RADIO_BEG_ADD = 12800
CON_RADIO_ENABLE_BEG_ADD = 12928
CON_FM_VFO_BEG_ADD = 12932
CON_ONE_RADIO_CH_DAT_CT = 4

# Map of bit-level settings for easier processing
# Key: (offset, start_bit, bit_count, type, metadata)
SETTING_MAP = {
    "BuleHoldTm": (7, 0, 4, "int", "Max: 15 (1S-15S, Infinite)"),
    "SpkGain": (8, 0, 4, "int", "Max: 4 (1-5 Level)"),
    "MicGain": (8, 4, 4, "int", "Max: 4 (1-5 Level)"),
    "VoxLev": (9, 0, 2, "int", "Max: 3 (Level 0-3)"),
    "VoxSw": (9, 2, 1, "bool", "0: OFF, 1: ON"),
    "RxFilter": (9, 3, 1, "bool", "0: OFF, 1: ON"),
    "TxFilter": (9, 4, 1, "bool", "0: OFF, 1: ON"),
    "LEDMode": (9, 5, 3, "int", "Max: 4 (On, 5S, 10S, 20S, 30S)"),
    "BlueSw": (10, 0, 1, "bool", "0: OFF, 1: ON"),
    "RxENCLev": (10, 1, 2, "int", "Max: 3 (OFF, Level 1, 2, 3)"),
    "VoiceChannel": (10, 3, 1, "bool", "0: Model 1, 1: Model 2"),
    "RepeaterMode": (10, 5, 2, "int", "Max: 2 (CROSS, A-TX, B-TX)"),
    "AutoLight": (10, 7, 1, "bool", "0: OFF, 1: ON"),
    "SqlLev": (12, 0, 5, "int", "Max: 9 (0-9 Level)"),
    "TailElim": (12, 5, 3, "int", "Max: 2 (OFF, Frequency, No Frequency)"),
    "TxChSelect": (13, 0, 1, "bool", "0: OFF, 1: ON"),
    "IntroScreen": (13, 3, 2, "int", "0: OFF, 1: Frequency, 2: Voltage"),
    "ScanType": (13, 5, 2, "int", "Max: 2 (To, Co, Se)"),
    "Double": (13, 7, 1, "bool", "0: OFF, 1: ON"),
    "TOT": (14, 0, 5, "int", "Max: 3 (OFF, 3, 5, 10 Minutes)"),
    "AutoPowerOff": (14, 5, 3, "int", "Max: 5 (OFF, 30, 60, 90, 120, 180 Minutes)"),
    "DisableMenu": (15, 0, 1, "bool", "0: OFF, 1: Inhibit menu/setup operations"),
    "DisableReset": (18, 6, 1, "bool", "0: OFF, 1: Inhibit factory reset"),
    "PasswordEnable": (18, 7, 1, "bool", "0: Password disabled, 1: Power-on password enabled"),

    # signaling selects
    "5Tone_SelectCh": (44, 0, 5, "int", "Max: 15 (Ch 1-16)"),
    "DTMF_SelectCh": (45, 0, 5, "int", "Max: 15 (Ch 1-16)"),
    "2Tone_SelectCh": (46, 0, 5, "int", "Max: 15 (Ch 1-16)"),
    "GPS_SelectCh": (29, 0, 5, "int", "Max: 31 (Ch 1-32)"),
}

# Helper for bit manipulation
def get_bits(byte, start, count):
    return (byte >> start) & ((1 << count) - 1)

def set_bits(byte, start, count, val):
    mask = ((1 << count) - 1) << start
    return (byte & ~mask) | ((val & ((1 << count) - 1)) << start)

def decode_bcd_freq(freq_bytes):
    # Tone frequencies are 2-byte LE, in 0.1Hz units
    return int.from_bytes(freq_bytes, byteorder='little') / 10.0

def encode_bcd_freq(freq_val):
    if not freq_val: return b'\x00\x00'
    val = int(round(float(freq_val) * 10))
    return val.to_bytes(2, byteorder='little')

def decode_signaling_id(data, length):
    # Signaling IDs are often stored as nibbles but we'll use hex chars for simplicity
    # A=A, B=B, C=C, D=D, E=*, F=# as per the programmer logic
    res = ""
    for i in range(length):
        byte_idx = i // 2
        nibble_idx = i % 2
        if byte_idx >= len(data): break
        b = data[byte_idx]
        nib = (b >> 4) if nibble_idx == 0 else (b & 0xF)
        if nib <= 9: res += str(nib)
        elif nib == 0xA: res += 'A'
        elif nib == 0xB: res += 'B'
        elif nib == 0xC: res += 'C'
        elif nib == 0xD: res += 'D'
        elif nib == 0xE: res += '*'
        elif nib == 0xF: res += '#'
    return res.rstrip('#').rstrip('*').rstrip('0') # Rough cleanup

def encode_signaling_id(s, length):
    # Reverse of decode_signaling_id
    res = bytearray((length + 1) // 2)
    for i, char in enumerate(s[:length]):
        nib = 0
        if char.isdigit(): nib = int(char)
        elif char == 'A': nib = 0xA
        elif char == 'B': nib = 0xB
        elif char == 'C': nib = 0xC
        elif char == 'D': nib = 0xD
        elif char == '*': nib = 0xE
        elif char == '#': nib = 0xF
        
        byte_idx = i // 2
        if i % 2 == 0:
            res[byte_idx] = (res[byte_idx] & 0x0F) | (nib << 4)
        else:
            res[byte_idx] = (res[byte_idx] & 0xF0) | nib
    return res

def decode_text_gbk(data):
    return data.decode('gbk', errors='ignore').strip('\x00').strip('\x20').strip()

def encode_text_gbk(text, length, pad=0x20):
    b = text.encode('gbk', errors='ignore')
    return b.ljust(length, bytes([pad]))[:length]

class ICFFile:
    def __init__(self):
        self.rows = [] # List of bytearrays, each 32 bytes

    def load(self, filename):
        with open(filename, 'r', newline='') as f:
            lines = f.readlines()
            self.header = lines[:FIEL_BEG_ROW]
            self.rows = []
            for line in lines[FIEL_BEG_ROW:]:
                strip_line = line.strip()
                if len(strip_line) < 6: continue
                try:
                    data = bytearray.fromhex(strip_line[6:])
                    self.rows.append(data)
                except: pass

    def save(self, filename):
        with open(filename, 'w', newline='\r\n') as f:
            for h in self.header:
                f.write(h.strip() + '\n')
            for i, row in enumerate(self.rows):
                offset = i * CON_ONE_ROW_DAT_CT
                f.write(f"{offset:04X}{len(row):02X}{row.hex().upper()}\n")

    def get_bytes(self, addr, length):
        row_idx = addr // CON_ONE_ROW_DAT_CT
        offset = addr % CON_ONE_ROW_DAT_CT
        
        full_data = bytearray()
        curr_row = row_idx
        while len(full_data) < offset + length:
            if curr_row < len(self.rows):
                full_data.extend(self.rows[curr_row])
            else:
                full_data.extend(bytearray([0x20] * 32))
            curr_row += 1
        
        return full_data[offset:offset+length]

    def set_bytes(self, addr, data):
        length = len(data)
        row_idx = addr // CON_ONE_ROW_DAT_CT
        offset = addr % CON_ONE_ROW_DAT_CT
        
        curr_row = row_idx
        data_pos = 0
        
        # First partial row
        first_row_len = min(length, CON_ONE_ROW_DAT_CT - offset)
        if curr_row >= len(self.rows):
            self.rows.extend([bytearray(32) for _ in range(curr_row - len(self.rows) + 1)])
        
        self.rows[curr_row][offset:offset+first_row_len] = data[0:first_row_len]
        data_pos += first_row_len
        curr_row += 1
        
        # Middle/End rows
        while data_pos < length:
            chunk_len = min(length - data_pos, CON_ONE_ROW_DAT_CT)
            if curr_row >= len(self.rows):
                self.rows.extend([bytearray(32) for _ in range(curr_row - len(self.rows) + 1)])
            self.rows[curr_row][0:chunk_len] = data[data_pos:data_pos+chunk_len]
            data_pos += chunk_len
            curr_row += 1

def decode_frequency(freq_bytes):
    # Frequencies are stored as 4 bytes, Little Endian BCD?
    # Class2.StringChgPro(text, 4) then Class2.StringChgFrePro(text, 5)
    # Let's verify BCD. Example: 145.000 MHz -> 00 00 50 14 in hex string?
    # Actually C# does: Convert.ToInt32(text, 16).ToString() then insert "."
    # So it is hex representation of the decimal value.
    # 145.0000 -> 1450000 -> 0x1620B0? No.
    # The image says 145.000. 
    # Let's re-read Class2.StringChgFrePro.
    # StrTemp = Convert.ToInt32(StrTemp, 16).ToString();
    # StrTemp = StrTemp.Insert(StrTemp.Length - data, ".");
    # So if hex is 01450000, it becomes "21299200"? No.
    # It must be actually stored as BCD or raw decimal value in hex.
    # "12345678" in hex string -> 0x12 0x34 0x56 0x78.
    # If it is Little Endian: 0x78 0x56 0x34 0x12.
    # string text = Class2.StringChgPro(text, 4); // Reverses 4 bytes (8 chars)
    # text = Class2.StringChgFrePro(text, 5); // ToInt32(hex, 16) then format.
    # Wait, ToInt32(..., 16) means it treats the hex string as a hexadecimal number.
    # example: hex string "0860A50D" -> reverses to "0DA56008" -> dec 228941832?
    # No, usually these radios use BCD. 145.0000 -> 14 50 00 00.
    # If it is 14 50 00 00, hex string is "14500000". Reversed: "00005014".
    # Int32("14500000", 16) = 340787200.
    # Let's check the encoder.py logic.
    pass

def decode_freq(freq_bytes):
    val = int.from_bytes(freq_bytes, byteorder='little')
    if val == 0xFFFFFFFF:
        return ""
    return f"{val / 100000:.5f}"

def decode_tone(tone_bytes, dcs_flag):
    val = int.from_bytes(tone_bytes, byteorder='little')
    if val == 0x0FFF:
        return "None"
    if dcs_flag:
        # DCS is stored as hex of the octal value
        # val is hex. converted to octal string.
        return f"{val:03o}"
    else:
        # CTCSS is val / 10
        return f"{val / 10:.1f}"

def encode_freq(freq_str):
    if not freq_str:
        return b'\xFF\xFF\xFF\xFF'
    try:
        val = int(round(float(freq_str) * 100000))
        return val.to_bytes(4, byteorder='little')
    except:
        return b'\xFF\xFF\xFF\xFF'

def encode_tone(tone_str, is_dcs):
    if not tone_str or tone_str == "None" or tone_str == "":
        return b'\xFF\x0F'
    try:
        if is_dcs:
            # Octal to hex
            val = int(tone_str, 8)
            return val.to_bytes(2, byteorder='little')
        else:
            # CTCSS * 10
            val = int(round(float(tone_str) * 10))
            return val.to_bytes(2, byteorder='little')
    except:
        return b'\xFF\x0F'


BUILTIN_TEMPLATE_HEADER = ['COM1', '#Comment=TYT INC.(C)  2013  #MapRev=1', '38400']
BUILTIN_TEMPLATE_ROWS_B85 = '''c%1E-Uq}>D6vn@~yQ`}{Na}<65F;YKXsqi-LP29$AtV`yfe@{x2vH!BWiK&=BvF)BsD%`WQ51xMB!tC;5|NrlU<Ce&Adv83rKcWZn=`XB?(F&}P}|kHN4~u~zcbgf-`u&ob7%S*rqQP=m>Nt4n5f0X;WkFH!1vBkM$(~EhevwGL9)R46Vo7BVDZ@`fn@D|v6hh@sDFO3PKWukos2|#`cW5M-GoMUOZV{V=APlz7rTe56O_>sUEPF6^>m~|7F(jd%S(ATyBpOl-80WjF;bHw9Y6wy9CFAZha7UqA%`4t$RURuZZ7!kZ6_nmtqRvzsBfuz7Xil%NEYaS+|EcAxMcUf)3+JP0vq?;Wh4u9svkrY8T8nDOi=p*3ndGJp3z<FS+}z^#fjWjIGvEdw&fS)Bzm-PV7WL~_RGCcvV2~zgB{4cKR6Re^HnwH(TlN>)ODfKn`LZ-XAsXDVnhrju|RUbl?Y^1H9JHxa_7ixukUzQTbl3WeqVhvwc+QUenhR~ljW=$^;Q;m3PsmqQEY~{deG<3ymWN30&pcK3sHGGF0M!@?lK)y-W{0+<-KO!Ra$etCOltC`64qPRTPU2&&NLRLNbGYLYrvr*7^h4?nDTO^nKj=1acc^L})ge|6!xI<&j<}a*|-Q!H7V0Eko0GhtWpndGOfGAuk>D%l@)MeX-)G=@C>XQDu3-Zf{9w>iayN0$;Jm{3?i}>p~7W<d8!S;|LDl90y5X+J<QFNGBt$4)M=x{r`4XAikjX8@<Aw+BLZfwd;5rwnFH=J4RzAZo*hk|H9QVC9k5;qtaSNK_Gh(uC-9SpZ|8B|FQNj<Q#0E<&M@Oy4~vj?LPk8KldL?|7*Q}6X|Ng*AJ5AQPB$i*IIw0W2=w9-OqpS-`@V$*R2*Ydj4-b<^0klkSwtAV>=^Rpw`{)<1YuULHTn7NNIzVc?WWC2Ndr;K<b86{t$9?50r*SK+_XQSDrz>^&Cp~3*c!#q=5m*!>^!xdJW7fkmiRV|9%H0;RBE{1}S?2^3Kmt_Dlk0Um;aZK|VDLrSUs(`3I!ya|o)RVWs02ll8xi?tk(1zrE*wto`%#zrDww`{(|*()wQ<d;=0)C5S?T|EF<~<J7<1$DjM>{_X7lFXg_<Cj'''

def load_builtin_template_icf():
    raw = zlib.decompress(base64.b85decode(BUILTIN_TEMPLATE_ROWS_B85.encode('ascii')))
    if len(raw) % CON_ONE_ROW_DAT_CT != 0:
        raise ValueError('Embedded template payload has invalid length')

    icf = ICFFile()
    icf.header = BUILTIN_TEMPLATE_HEADER.copy()
    icf.rows = [
        bytearray(raw[i:i + CON_ONE_ROW_DAT_CT])
        for i in range(0, len(raw), CON_ONE_ROW_DAT_CT)
    ]
    return icf

def main():
    if len(sys.argv) < 2:
        print("Usage: icf_tool.py <command> ...")
        return

    cmd = sys.argv[1]
    if cmd == "decode":
        if len(sys.argv) < 3:
            print("Usage: icf_tool.py decode <input.icf> [out_channels.csv] [out_settings.csv]")
            return
        
        input_icf = sys.argv[2]
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        base_name = os.path.splitext(os.path.basename(input_icf))[0]
        
        out_channels = sys.argv[3] if len(sys.argv) > 3 else f"{base_name}-{date_str}-channels.csv"
        out_settings = sys.argv[4] if len(sys.argv) > 4 else f"{base_name}-{date_str}-settings.csv"
            
        icf = ICFFile()
        icf.load(input_icf)
        
        # 1. Channels (Main)
        with open(out_channels, 'w', newline='') as f:
            writer = csv.writer(f)
            # CHIRP Standard Headers
            writer.writerow(["Location","Name","Frequency","Duplex","Offset","Tone","rToneFreq","cToneFreq","DtcsCode","DtcsPolarity","RxDtcsCode","CrossMode","Mode","TStep","Skip","Power","Comment","URCALL","RPT1CALL","RPT2CALL","DVCODE"])
            
            active_masks = icf.get_bytes(CH_INF_BEG_ADDR, 25) # 200 bits
            skip_masks = icf.get_bytes(CH_SKIP_BEG_ADDR, 25)
            
            for i in range(200):
                if not (active_masks[i // 8] & (1 << (i % 8))): continue
                
                data = icf.get_bytes(CH_INF_ADDR + i * CON_ONE_CH_DAT_CT, CON_ONE_CH_DAT_CT)
                
                rx_val = int.from_bytes(data[0:4], 'little')
                tx_val = int.from_bytes(data[4:8], 'little')
                if rx_val == 0xFFFFFFFF: continue
                
                rx_f = f"{rx_val / 100000:.6f}"
                
                duplex = ""
                offset = "0.000000"
                if rx_val != tx_val:
                    if tx_val > rx_val: duplex, offset = "+", f"{(tx_val - rx_val)/100000:.6f}"
                    else: duplex, offset = "-", f"{(rx_val - tx_val)/100000:.6f}"
                
                # Tone Reconstruction
                rtw, ctw = int.from_bytes(data[8:10], 'little'), int.from_bytes(data[10:12], 'little')
                r_v, c_v = rtw & 0x0FFF, ctw & 0x0FFF
                
                # Rules: Value <= 511 is DCS, > 511 is CTCSS. 0xFFF is OFF.
                r_is_d = (r_v <= 511 and r_v != 0x0FFF)
                c_is_d = (c_v <= 511 and c_v != 0x0FFF)
                r_is_ct = (r_v > 511 and r_v != 0x0FFF)
                c_is_ct = (c_v > 511 and c_v != 0x0FFF)
                
                # CHIRP column mapping (per CHIRP docs):
                #   rToneFreq = "Tone"    = TX CTCSS tone (from ctw/c_v)
                #   cToneFreq = "ToneSql" = RX CTCSS squelch (from rtw/r_v)
                tone_tx = f"{c_v/10:.1f}" if c_is_ct else "88.5"
                tone_rx = f"{r_v/10:.1f}" if r_is_ct else "88.5"
                
                # DCS code values (octal, 3-digit, no decimals)
                # DtcsCode = TX DCS code, RxDtcsCode = RX DCS code
                d_code = f"{c_v:03o}" if c_is_d else "023"
                rd_code = f"{r_v:03o}" if r_is_d else "023"
                
                # Polarities: first char = TX, second char = RX
                tp = "R" if (ctw & 0x8000) else "N"
                rp = "R" if (rtw & 0x4000) else "N"
                pol = tp + rp
                
                # Determine CHIRP Tone mode and CrossMode
                # RX = decode (what we listen for), TX = encode (what we transmit)
                rx_type = "DTCS" if r_is_d else "Tone" if r_is_ct else ""
                tx_type = "DTCS" if c_is_d else "Tone" if c_is_ct else ""
                
                tone_mode = ""
                cross_mode = "Tone->Tone"
                
                if tx_type == "" and rx_type == "":
                    tone_mode = ""  # No tone
                elif tx_type == "Tone" and rx_type == "":
                    tone_mode = "Tone"  # TX CTCSS only
                elif tx_type == "Tone" and rx_type == "Tone" and r_v == c_v:
                    tone_mode = "TSQL"  # Same CTCSS both ways
                elif tx_type == "DTCS" and rx_type == "DTCS" and r_v == c_v:
                    tone_mode = "DTCS"  # Same DCS code both ways
                    rd_code = "023"  # CHIRP: RxDtcsCode unused in simple DTCS
                else:
                    # Any other combination is Cross mode
                    tone_mode = "Cross"
                    cross_mode = f"{tx_type}->{rx_type}"
                
                # Split names: 6 bytes in record, 10 bytes in overflow
                r_name = data[15:21]
                o_name = icf.get_bytes(CH_INF_NAME_ADDR + i * 10, 10)
                name = decode_text_gbk(r_name + o_name)
                
                f12 = data[12]
                power = ["70W", "25W", "10W"][(f12 & 0xC0) >> 6] if (f12 & 0xC0) >> 6 < 3 else "70W"
                mode = ["FM", "FM", "NFM"][(f12 & 0x30) >> 4] if (f12 & 0x30) >> 4 < 3 else "FM"
                
                # Skip is 'S' if bit is 0 (Disabled), empty if bit is 1 (Enabled)
                skip = "" if (skip_masks[i // 8] & (1 << (i % 8))) else "S"
                
                # Location is 0-based for CHIRP
                #   rToneFreq=tone_tx, cToneFreq=tone_rx per CHIRP convention
                writer.writerow([i, name, rx_f, duplex, offset, tone_mode, tone_tx, tone_rx, d_code, pol, rd_code, cross_mode, mode, "2.50", skip, power, "", "", "", "", ""])

        # 2. Settings (Global + Signaling + GPS + Radio)
        with open(out_settings, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Key", "Value", "Metadata"])
            
            # Global Settings
            global_set = icf.get_bytes(CON_SET_BEG_ADDR, 64)
            for key, (off, start, count, type, metadata) in SETTING_MAP.items():
                val = get_bits(global_set[off], start, count)
                writer.writerow([key, val if type == "int" else (1 if val else 0), metadata])
            
            password = decode_text_gbk(global_set[26:32])
            writer.writerow(["Password", password])
            
            # DTMF Settings & Channels
            dtmf_set = icf.get_bytes(CON_DTMF_SET_ADDR, 64)
            writer.writerow(["DTMF_OwnID", decode_signaling_id(dtmf_set[9:14], 8)])
            writer.writerow(["DTMF_Mask", dtmf_set[7:9].hex().upper()])
            for i in range(16):
                ch_data = icf.get_bytes(CON_DTMF_CH_ADDR + i * CON_ONE_DTMF_CH_DAT_CT, CON_ONE_DTMF_CH_DAT_CT)
                writer.writerow([f"DTMF_Ch{i+1:02}_Code", decode_signaling_id(ch_data[0:12], 24)])
                writer.writerow([f"DTMF_Ch{i+1:02}_Type", ch_data[12] >> 5]) # 0=Own, 1=Group, 2=Select
            
            # 2Tone Settings & Channels
            tone2_rx = icf.get_bytes(CON_TONE2_RX_ADDR, 16)
            writer.writerow(["2Tone_ATone", decode_bcd_freq(tone2_rx[0:2])])
            writer.writerow(["2Tone_BTone", decode_bcd_freq(tone2_rx[2:4])])
            writer.writerow(["2Tone_CTone", decode_bcd_freq(tone2_rx[4:6])])
            writer.writerow(["2Tone_DTone", decode_bcd_freq(tone2_rx[6:8])])
            writer.writerow(["2Tone_Mask", tone2_rx[14:16].hex().upper()])
            for i in range(16):
                ch_data = icf.get_bytes(CON_TONE2_CH_ADDR + i * CON_ONE_TONE2_CH_DAT_CT, CON_ONE_TONE2_CH_DAT_CT)
                writer.writerow([f"2Tone_Ch{i+1:02}_First", decode_bcd_freq(ch_data[0:2])])
                writer.writerow([f"2Tone_Ch{i+1:02}_Second", decode_bcd_freq(ch_data[2:4])])
                writer.writerow([f"2Tone_Ch{i+1:02}_Name", decode_text_gbk(ch_data[4:10])])

            # 5Tone Settings & Channels
            t5_set = icf.get_bytes(CON_TONE5_SET_ADDR, 32)
            writer.writerow(["5Tone_OwnID", decode_signaling_id(t5_set[0:5], 8)])
            writer.writerow(["5Tone_TXMask", t5_set[22:24].hex().upper()])
            writer.writerow(["5Tone_RXMask", bytes([t5_set[24]]).hex().upper()])
            for i in range(16):
                tx_ch = icf.get_bytes(CON_TONE5_TX_ADDR + i * CON_ONE_TONE5_TX_DAT_CT, CON_ONE_TONE5_TX_DAT_CT)
                writer.writerow([f"5Tone_TX{i+1:02}_CallID", decode_signaling_id(tx_ch[0:5], 8)])
                writer.writerow([f"5Tone_TX{i+1:02}_Name", decode_text_gbk(tx_ch[22:28])])
            for i in range(8):
                rx_ch = icf.get_bytes(CON_TONE5_RX_ADDR + i * CON_ONE_TONE5_RX_DAT_CT, CON_ONE_TONE5_RX_DAT_CT)
                writer.writerow([f"5Tone_RX{i+1:02}_Code", decode_signaling_id(rx_ch[1:7], 12)])
                writer.writerow([f"5Tone_RX{i+1:02}_Name", decode_text_gbk(rx_ch[8:14])])

            # GPS Contacts & Settings
            gps_set = icf.get_bytes(CON_GPS_SET_ADDR, 32)
            writer.writerow(["GPS_OwnID", decode_signaling_id(gps_set[4:9], 8)])
            writer.writerow(["GPS_Mask", gps_set[0:4].hex().upper()])
            for i in range(32):
                ch_data = icf.get_bytes(CON_GPS_CH_ADDR + i * CON_ONE_GPS_CH_DAT_CT, CON_ONE_GPS_CH_DAT_CT)
                writer.writerow([f"GPS_Ch{i+1:02}_ID", decode_signaling_id(ch_data[0:5], 8)])

            # FM Radio
            for i in range(24):
                freq_bytes = icf.get_bytes(CON_RADIO_BEG_ADD + i * 4, 4)
                if freq_bytes == b'\x20\x20\x20\x20' or freq_bytes == b'\x00\x00\x00\x00':
                    continue
                freq = decode_freq(freq_bytes)
                if freq and freq != "0.00000":
                    writer.writerow([f"FM_Ch{i+1:02}", freq])
            
            vfo_bytes = icf.get_bytes(CON_FM_VFO_BEG_ADD, 4)
            if vfo_bytes != b'\x20\x20\x20\x20' and vfo_bytes != b'\x00\x00\x00\x00':
                vfo = decode_freq(vfo_bytes)
                if vfo and vfo != "0.00000":
                    writer.writerow(["FM_VFO", vfo])
        
        print(f"Decoded to {out_channels} and {out_settings}")

    elif cmd == "encode":
        if len(sys.argv) < 5:
            print("Usage: icf_tool.py encode <in_channels.csv> <in_settings.csv> <output.icf> [template.icf]")
            return
            
        if len(sys.argv) > 5:
            icf = ICFFile()
            icf.load(sys.argv[5])
        else:
            # Use an embedded factory image so untouched regions preserve
            # radio defaults exactly like passing template.icf explicitly.
            icf = load_builtin_template_icf()
            
        settings = {}
        with open(sys.argv[3], 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                settings[row["Key"]] = row["Value"]

        # 1. Global Settings
        global_set = bytearray(icf.get_bytes(CON_SET_BEG_ADDR, 64))
        for key, info in SETTING_MAP.items():
            off, start, count, type_str, metadata = info
            if key in settings:
                try:
                    val = int(float(settings[key]))
                    global_set[off] = set_bits(global_set[off], start, count, val)
                except: pass
        if "Password" in settings:
            pwd = settings["Password"].strip()
            global_set[26:32] = encode_text_gbk(pwd, 6)
        icf.set_bytes(CON_SET_BEG_ADDR, global_set)

        # 2. Signaling Global Settings
        # DTMF
        dtmf_set = bytearray(icf.get_bytes(CON_DTMF_SET_ADDR, 64))
        if "DTMF_OwnID" in settings:
            new_id = encode_signaling_id(settings["DTMF_OwnID"], 8)
            dtmf_set[9:9+len(new_id)] = new_id
        
        # Automate DTMF Mask
        dtmf_mask = 0
        for i in range(16):
            if f"DTMF_Ch{i+1:02}_Code" in settings:
                dtmf_mask |= (1 << i)
        dtmf_set[7:9] = dtmf_mask.to_bytes(2, 'little')
        icf.set_bytes(CON_DTMF_SET_ADDR, dtmf_set)

        # 2Tone
        tone2_rx = bytearray(icf.get_bytes(CON_TONE2_RX_ADDR, 16))
        for k, off in [("2Tone_ATone", 0), ("2Tone_BTone", 2), ("2Tone_CTone", 4), ("2Tone_DTone", 6)]:
            if k in settings: tone2_rx[off:off+2] = encode_bcd_freq(settings[k])
        
        # Automate 2Tone Mask
        tone2_mask = 0
        for i in range(16):
            if f"2Tone_Ch{i+1:02}_First" in settings:
                tone2_mask |= (1 << i)
        tone2_rx[14:16] = tone2_mask.to_bytes(2, 'little')
        icf.set_bytes(CON_TONE2_RX_ADDR, tone2_rx)

        # 5Tone
        t5_set = bytearray(icf.get_bytes(CON_TONE5_SET_ADDR, 32))
        if "5Tone_OwnID" in settings:
            new_id = encode_signaling_id(settings["5Tone_OwnID"], 8)
            t5_set[0:len(new_id)] = new_id
        
        # Automate 5Tone Masks
        t5_tx_mask = 0
        for i in range(16):
            if f"5Tone_TX{i+1:02}_CallID" in settings:
                t5_tx_mask |= (1 << i)
        t5_set[22:24] = t5_tx_mask.to_bytes(2, 'little')
        
        t5_rx_mask = 0
        for i in range(8):
            if f"5Tone_RX{i+1:02}_Code" in settings:
                t5_rx_mask |= (1 << i)
        t5_set[24] = t5_rx_mask
        icf.set_bytes(CON_TONE5_SET_ADDR, t5_set)

        # GPS
        gps_set = bytearray(icf.get_bytes(CON_GPS_SET_ADDR, 32))
        if "GPS_OwnID" in settings:
            new_id = encode_signaling_id(settings["GPS_OwnID"], 8)
            gps_set[4:4+len(new_id)] = new_id
        
        # Automate GPS Mask
        gps_mask = 0
        for i in range(32):
            if f"GPS_Ch{i+1:02}_ID" in settings:
                gps_mask |= (1 << i)
        gps_set[0:4] = gps_mask.to_bytes(4, 'little')
        icf.set_bytes(CON_GPS_SET_ADDR, gps_set)

        # 3. Signaling Channels (Update only)
        for i in range(16):
            # DTMF
            k = f"DTMF_Ch{i+1:02}_Code"
            if k in settings:
                ch_data = bytearray(icf.get_bytes(CON_DTMF_CH_ADDR + i * CON_ONE_DTMF_CH_DAT_CT, CON_ONE_DTMF_CH_DAT_CT))
                new_id = encode_signaling_id(settings[k], 24)
                ch_data[0:len(new_id)] = new_id
                tk = f"DTMF_Ch{i+1:02}_Type"
                if tk in settings: ch_data[12] = (ch_data[12] & 0x1F) | ((int(settings[tk]) & 7) << 5)
                icf.set_bytes(CON_DTMF_CH_ADDR + i * CON_ONE_DTMF_CH_DAT_CT, ch_data)
            # 2Tone
            f_key, s_key, n_key = f"2Tone_Ch{i+1:02}_First", f"2Tone_Ch{i+1:02}_Second", f"2Tone_Ch{i+1:02}_Name"
            if f_key in settings:
                ch_data = bytearray(icf.get_bytes(CON_TONE2_CH_ADDR + i * CON_ONE_TONE2_CH_DAT_CT, CON_ONE_TONE2_CH_DAT_CT))
                ch_data[0:2] = encode_bcd_freq(settings[f_key])
                if s_key in settings: ch_data[2:4] = encode_bcd_freq(settings[s_key])
                if n_key in settings: ch_data[4:10] = encode_text_gbk(settings[n_key], 6)
                icf.set_bytes(CON_TONE2_CH_ADDR + i * CON_ONE_TONE2_CH_DAT_CT, ch_data)
            # 5Tone TX
            c_key, n_key = f"5Tone_TX{i+1:02}_CallID", f"5Tone_TX{i+1:02}_Name"
            if c_key in settings:
                tx_ch = bytearray(icf.get_bytes(CON_TONE5_TX_ADDR + i * CON_ONE_TONE5_TX_DAT_CT, CON_ONE_TONE5_TX_DAT_CT))
                new_id = encode_signaling_id(settings[c_key], 8)
                tx_ch[0:len(new_id)] = new_id
                if n_key in settings: tx_ch[22:28] = encode_text_gbk(settings[n_key], 6)
                icf.set_bytes(CON_TONE5_TX_ADDR + i * CON_ONE_TONE5_TX_DAT_CT, tx_ch)
        for i in range(8):
            # 5Tone RX
            c_key, n_key = f"5Tone_RX{i+1:02}_Code", f"5Tone_RX{i+1:02}_Name"
            if c_key in settings:
                rx_ch = bytearray(icf.get_bytes(CON_TONE5_RX_ADDR + i * CON_ONE_TONE5_RX_DAT_CT, CON_ONE_TONE5_RX_DAT_CT))
                new_id = encode_signaling_id(settings[c_key], 12)
                rx_ch[1:1+len(new_id)] = new_id
                if n_key in settings: rx_ch[8:14] = encode_text_gbk(settings[n_key], 6)
                icf.set_bytes(CON_TONE5_RX_ADDR + i * CON_ONE_TONE5_RX_DAT_CT, rx_ch)
        for i in range(32):
            # GPS
            id_key = f"GPS_Ch{i+1:02}_ID"
            if id_key in settings:
                ch_data = bytearray(icf.get_bytes(CON_GPS_CH_ADDR + i * CON_ONE_GPS_CH_DAT_CT, CON_ONE_GPS_CH_DAT_CT))
                new_id = encode_signaling_id(settings[id_key], 8)
                ch_data[0:len(new_id)] = new_id
                icf.set_bytes(CON_GPS_CH_ADDR + i * CON_ONE_GPS_CH_DAT_CT, ch_data)

        # 4. FM Radio
        fm_masks = bytearray(4)
        for i in range(24):
            k = f"FM_Ch{i+1:02}"
            if k in settings:
                icf.set_bytes(CON_RADIO_BEG_ADD + i * 4, encode_freq(settings[k]))
                fm_masks[i // 8] |= (1 << (i % 8))
        icf.set_bytes(CON_RADIO_ENABLE_BEG_ADD, fm_masks)
        if "FM_VFO" in settings: icf.set_bytes(CON_FM_VFO_BEG_ADD, encode_freq(settings["FM_VFO"]))

        # 5. Main Channels
        with open(sys.argv[2], 'r') as f:
            reader = csv.DictReader(f)
            # Rebuild masks from scratch
            active_masks, skip_masks = bytearray(25), bytearray(25)
            for row in reader:
                try:
                    loc = int(row.get("Location") or 0)
                    if loc < 0 or loc >= 200: continue
                except: continue
                
                name = row.get("Name") or ""
                rx_f = float(row.get("Frequency") or 0)
                duplex, off_str = row.get("Duplex") or "", row.get("Offset") or "0.000000"
                tx_f = rx_f + (float(off_str) if duplex == "+" else -float(off_str) if duplex == "-" else 0)
                
                data = bytearray(icf.get_bytes(CH_INF_ADDR + loc * 21, 21))
                data[0:4], data[4:8] = encode_freq(str(rx_f)), encode_freq(str(tx_f))
                
                t_mode = row.get("Tone") or ""
                # CHIRP: rToneFreq="Tone"=TX tone, cToneFreq="ToneSql"=RX squelch
                tone_tx = row.get("rToneFreq") or "88.5"  # TX CTCSS
                tone_rx = row.get("cToneFreq") or "88.5"  # RX CTCSS
                d_code = row.get("DtcsCode") or "023"      # TX DCS
                rd_code = row.get("RxDtcsCode") or "023"   # RX DCS
                pol = row.get("DtcsPolarity") or "NN"       # TX pol + RX pol
                
                # Default bytes: Inactive Tone
                # rtw = radio RX (decode), ctw = radio TX (encode)
                rtw, ctw = 0x0FFF, 0x0FFF
                
                if t_mode == "Tone":
                    # CHIRP: Tone mode uses rToneFreq ("Tone") for TX
                    val = int(float(tone_tx) * 10)
                    ctw = val & 0x0FFF
                elif t_mode == "TSQL":
                    # CHIRP: TSQL mode uses cToneFreq ("ToneSql") for both
                    val = int(float(tone_rx) * 10)
                    rtw, ctw = val & 0x0FFF, val & 0x0FFF
                elif t_mode == "DTCS":
                    cv = int(d_code, 8)
                    rv = cv  # CHIRP DTCS mode: same code for both TX and RX
                    # pol[0]=TX polarity, pol[1]=RX polarity
                    rtw = (rv & 0x0FFF) | (0x4000 if pol[1:2] == "R" else 0)
                    ctw = (cv & 0x0FFF) | (0x8000 if pol[0:1] == "R" else 0)
                elif t_mode == "Cross":
                    cross_mode = row.get("CrossMode") or "Tone->Tone"
                    cross_parts = cross_mode.split("->")
                    # CrossMode format: "TX_type->RX_type"
                    tx_type = cross_parts[0].strip() if len(cross_parts) > 0 else "Tone"
                    rx_type = cross_parts[1].strip() if len(cross_parts) > 1 else "Tone"
                    # RX side (radio decode = rtw)
                    if rx_type == "DTCS":
                        rv = int(rd_code, 8)
                        rtw = (rv & 0x0FFF) | (0x4000 if pol[1:2] == "R" else 0)
                    elif rx_type == "Tone":
                        rv = int(float(tone_rx) * 10)
                        rtw = rv & 0x0FFF
                    # TX side (radio encode = ctw)
                    if tx_type == "DTCS":
                        cv = int(d_code, 8)
                        ctw = (cv & 0x0FFF) | (0x8000 if pol[0:1] == "R" else 0)
                    elif tx_type == "Tone":
                        cv = int(float(tone_tx) * 10)
                        ctw = cv & 0x0FFF

                data[8:10], data[10:12] = rtw.to_bytes(2, 'little'), ctw.to_bytes(2, 'little')
                
                # Update Tone Signaling Enable Flag (bit 5 of data[13])
                if rtw != 0x0FFF or ctw != 0x0FFF:
                    data[13] |= 0x20
                else:
                    data[13] &= ~0x20
                
                mode_str, p_str = row.get("Mode") or "FM", row.get("Power") or "70.0W"
                w_val = 2 if "N" in mode_str else 0
                p_val = 1 if ("25" in p_str or "Mid" in p_str) else 2 if ("10" in p_str or "Low" in p_str) else 0
                data[12] = (data[12] & 0x0F) | (w_val << 4) | (p_val << 6)
                
                # Split Name: 6 bytes in record (from byte 15), 10 bytes in overflow (offset 8960)
                data[15:21] = encode_text_gbk(name[:6], 6)
                icf.set_bytes(CH_INF_ADDR + loc * 21, data)
                icf.set_bytes(CH_INF_NAME_ADDR + loc * 10, encode_text_gbk(name[6:16], 10))
                
                active_masks[loc // 8] |= (1 << (loc % 8))
                # Skip in CSV 'S' means bit should be 0. Empty means bit should be 1.
                if (row.get("Skip") or "").strip() != "S": skip_masks[loc // 8] |= (1 << (loc % 8))

        icf.set_bytes(CH_INF_BEG_ADDR, active_masks)
        icf.set_bytes(CH_SKIP_BEG_ADDR, skip_masks)
        icf.save(sys.argv[4])
        print(f"Encoded to {sys.argv[4]}")
    elif cmd == "updatetemplate":
        if len(sys.argv) < 3:
            print("Usage: icf_tool.py updatetemplate <new_template.icf>")
            return
            
        new_template_icf = sys.argv[2]
        icf = ICFFile()
        icf.load(new_template_icf)
        
        raw_data = bytearray()
        for row in icf.rows:
            raw_data.extend(row)
            
        compressed = zlib.compress(raw_data)
        b85 = base64.b85encode(compressed).decode('ascii')
        
        # Rewrite icf_tool.py with the new base85 string
        with open(__file__, 'r', encoding='utf-8') as f:
            content = f.read()
            
        import re
        new_content = re.sub(
            r"(BUILTIN_TEMPLATE_ROWS_B85\s*=\s*''')(.*?)(''')",
            rf"\g<1>{b85}\g<3>",
            content,
            flags=re.DOTALL
        )
        
        with open(__file__, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"Successfully updated embedded template in {os.path.basename(__file__)} using {new_template_icf}")

    else:
        print("Unknown command. Use 'decode', 'encode', or 'updatetemplate'.")

if __name__ == "__main__":
    main()


