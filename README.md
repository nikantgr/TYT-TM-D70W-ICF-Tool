# TYT TM-D70W ICF Tool

A bidirectional converter between radio `.icf` files and CHIRP-compatible CSV files.
It lets you edit channels and advanced settings in spreadsheets, then rebuild a valid radio image.

## Author

**Nikos K. Kantarakias — SV1TSD**  
YouTube: [youtube.com/@NikosKantarakias](https://youtube.com/@NikosKantarakias)

---

## Key Features

- **CHIRP-compatible channels CSV** export/import.
- **Advanced settings CSV** for radio-wide configuration and signaling.
- **FM radio support** for all 24 broadcast memory channels plus FM VFO.
- **Signaling support** for DTMF, 2-Tone, 5-Tone, and GPS lists.
- **Automatic mask reconstruction** (active bits are derived from CSV content).

---

## Usage

### 1) Decode ICF to CSV

```bash
python icf_tool.py decode <input.icf> [out_channels.csv] [out_settings.csv]
```

- `input.icf`: source radio configuration file.
- `out_channels.csv` (optional): defaults to `<filename>-YYYYMMDD-channels.csv`.
- `out_settings.csv` (optional): defaults to `<filename>-YYYYMMDD-settings.csv`.

### 2) Encode CSV to ICF

```bash
python icf_tool.py encode <in_channels.csv> <in_settings.csv> <output.icf> [template.icf]
```

- `in_channels.csv`: CHIRP-style channels CSV.
- `in_settings.csv`: advanced settings/signaling CSV.
- `output.icf`: generated output file.
- `template.icf` (optional):
  - if provided, used as the base image;
  - if omitted, embedded template is used automatically.

## CSV Sections

### `channels.csv`

Uses standard CHIRP columns.

- `Mode`: use `FM` (wide) or `NFM` (narrow).
- `Tone`, `rToneFreq`, `cToneFreq`, `DtcsCode`, `RxDtcsCode`, `DtcsPolarity`: tone/digital signaling info.
- `Power`: e.g. `70.0W`, `25.0W`, `10.0W`.
- `Skip`: `S` means skipped in scan; blank means included.

### `settings.csv`

Contains everything outside main channels:

1. **Global settings** (e.g. `MicGain`, `SqlLev`, `LEDMode`).
2. **FM radio channels** (`FM_Ch01` ... `FM_Ch24`) and `FM_VFO`.
3. **Signaling**:
   - DTMF: own ID + per-channel code/type
   - 2-Tone: tone banks + per-channel pair/name
   - 5-Tone: own ID + TX/RX entries
   - GPS: own ID + per-channel IDs

## Automatic Behaviors

- **Mask rebuilding**:
  - channel active mask,
  - skip mask,
  - FM active mask,
  - DTMF/2-Tone/5-Tone/GPS enable masks.
- **Mode mapping**:
  - radio wide/middle -> CHIRP `FM`,
  - radio narrow -> CHIRP `NFM`,
  - CHIRP `FM` writes radio wide by default,
  - CHIRP `NFM` writes radio narrow.

---

## Notes

- Text fields are encoded in **GBK**.
- The tool intentionally writes only known mapped fields and leaves unknown regions untouched relative to the selected base image.

---

## Disclaimer

This tool is provided **as-is, without warranty of any kind**, express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, or non-infringement.

Use entirely at your own risk. The author accepts **no liability** for:

- damage to radio hardware, firmware, or configuration resulting from use of this tool;
- loss of data, misconfiguration, or operational failure of any device;
- any direct, indirect, incidental, or consequential damages arising from use or inability to use this software.

It is the user's sole responsibility to verify the correctness of any generated `.icf` file before programming a radio. Always back up your original `.icf` file before use.

Compliance with local radio regulations (frequency allocations, power limits, licensing requirements) is the user's responsibility. The author bears no liability for unlawful radio operation.

---


## License

Copyright (C) 2026 SV1TSD Nikos ?. Kantarakias

This program is free software: you can redistribute it and/or modify it under the terms of the **GNU Affero General Public License** as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

