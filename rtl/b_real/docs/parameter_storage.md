# Member B parameter-storage preparation

Member A's frozen tensors are small enough to keep on chip:

| Item | Count/bytes |
|---|---:|
| INT8 weights | 2,832 bytes |
| INT32 biases | 208 bytes |
| Q1.15 PReLU slopes | 96 bytes |
| signed Q31 multipliers | 208 bytes |
| Total | **3,344 bytes** |

This total excludes replicated banks needed to feed many parallel MAC lanes.
The capacity is small, but read bandwidth and banking remain architecture
constraints.

Member A supplied weights, biases, and PReLU values in NPY/BIN/MEM/COE forms.
Q31 multipliers are authoritative in `quant_params.json` but were not exported
as memory files. Member B's `scripts/export_requant_q31.py` reproducibly emits
little-endian BIN, hexadecimal MEM, COE, and a manifest tied to the source JSON
SHA-256. Generated files are derived build artifacts, not rewritten member-A
source data.

`rtl/memory/sync_parameter_rom.sv` is a transport-neutral synchronous ROM
consumer. The final number of banks and address schedule must follow the
parallelism plan and member C's clock/board constraints.
