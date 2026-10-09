"""Read saved PHY0 UART bytes only; no serial/network/JTAG or writes."""
import argparse
import binascii
import json
from pathlib import Path
import struct


FAILURES = {
    0: "OK", 1: "ID2_NO_ACK", 2: "ID3_NO_ACK", 3: "IDENTITY_MISMATCH",
    4: "SAVE_PAGE_NO_ACK", 5: "SELECT_PAGE_NO_ACK", 6: "SELECT_PAGE_MISMATCH",
    7: "RX_INITIAL_NO_ACK", 8: "RX_INITIAL_DELAY_OFF", 9: "TX_INITIAL_NO_ACK",
    10: "TX_ACTUAL_NO_ACK", 11: "TX_ACTUAL_FULL_WORD_MISMATCH",
    12: "RX_ACTUAL_NO_ACK", 13: "RX_ACTUAL_DELAY_OFF",
    14: "RESTORE_NO_ACK", 15: "RESTORE_PAGE_MISMATCH", 255: "INTERNAL_STATE_ERROR",
}


def parse_packet(raw: bytes) -> dict:
    if len(raw) != 32:
        raise ValueError(f"Expected 32 bytes, got {len(raw)}")
    if raw[:4] != b"PHY0" or raw[4:6] != bytes((1, 32)):
        raise ValueError("Magic/version/length mismatch")
    crc = binascii.crc_hqx(raw[:30], 0xFFFF)
    if int.from_bytes(raw[30:32], "little") != crc:
        raise ValueError("CRC16-CCITT-FALSE mismatch")
    if raw[6] & 0x80 or raw[29] or raw[10] != 5:
        raise ValueError("Reserved/address field mismatch")
    flags = dict(zip(("cfg_ok", "cfg_failed", "identity_ok", "page_saved",
                      "tx_write_attempted", "restore_verified", "cfg_done"),
                     (bool(raw[6] & (1 << x)) for x in range(7))))
    names = ("id2", "id3", "tx_old", "tx_actual", "rx_old", "rx_actual",
             "original_page", "restored_page")
    values = dict(zip(names, struct.unpack("<8H", raw[12:28])))
    failure, restore_failure, attempts, valid, state = raw[7], raw[8], raw[9], raw[11], raw[28]
    if not flags["cfg_done"] or state != 13 or attempts > 2 or restore_failure > 2:
        raise ValueError("Nonterminal or invalid diagnostic fields")
    if flags["cfg_ok"] == flags["cfg_failed"]:
        raise ValueError("Exactly one of cfg_ok/cfg_failed must be true")
    if flags["identity_ok"] and (valid & 3 != 3 or values["id2"] != 0x001C or values["id3"] != 0xC916):
        raise ValueError("Identity flag lacks exact identity evidence")
    if flags["page_saved"] and (not flags["identity_ok"] or not valid & 4):
        raise ValueError("Page save lacks identity/validity evidence")
    if flags["tx_write_attempted"] and (not flags["page_saved"] or (valid & 0x18) != 0x18 or
                                       not values["rx_old"] & 8 or not values["tx_old"] & 0x100):
        raise ValueError("TX write lacks original RX/TX evidence")
    if flags["restore_verified"] and (not flags["page_saved"] or not valid & 0x80 or
                                     not attempts or values["restored_page"] != values["original_page"]):
        raise ValueError("Restoration flag lacks page readback evidence")
    if flags["cfg_ok"] and (failure or restore_failure or valid != 0xFF or attempts != 1 or
                            not all(flags[x] for x in ("identity_ok", "page_saved", "restore_verified")) or
                            values["tx_actual"] != values["tx_old"] & 0xFEFF or
                            flags["tx_write_attempted"] != bool(values["tx_old"] & 0x100) or
                            not values["rx_old"] & 8 or not values["rx_actual"] & 8):
        raise ValueError("Success flag lacks ALL configuration evidence")
    if flags["cfg_failed"] and failure == 0:
        raise ValueError("Failure flag without failure code")
    if failure not in FAILURES:
        raise ValueError("Unknown failure code")
    return dict(format="PHY0/v1/32B/CRC16-CCITT-FALSE", scope="saved_UART_status_only_no_bitstream_binding",
                flags=flags, failure_code=failure, failure_name=FAILURES[failure],
                restore_failure_code=restore_failure, restore_attempts=attempts,
                diag_valid=f"0x{valid:02x}", terminal_state=state,
                registers={k: f"0x{v:04x}" for k, v in values.items()},
                actual_success_rx1_tx0=flags["cfg_ok"],
                all_other_tx_bits_preserved=(bool(valid & 0x30 == 0x30) and
                                            values["tx_actual"] & 0xFEFF == values["tx_old"] & 0xFEFF),
                crc16=f"0x{crc:04x}")


def parse_capture(raw: bytes, minimum_packets: int = 2) -> dict:
    if minimum_packets < 1:
        raise ValueError("Minimum packet count must be positive")
    locations = [i for i in range(len(raw)) if raw.startswith(b"PHY0", i)]
    if len(locations) < minimum_packets:
        raise ValueError(f"Expected at least {minimum_packets} PHY0 packets, got {len(locations)}")
    packets = [raw[i:i + 32] for i in locations]
    decoded = [parse_packet(p) for p in packets]
    if any(p != packets[0] for p in packets):
        raise ValueError("Repeated cached startup packets differ")
    return dict(packet_count=len(packets), repeated_bytes_identical=True,
                offsets=locations, status=decoded[0])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture", type=Path)
    p.add_argument("--scan", action="store_true", help="Validate identical cached packets in a larger saved capture")
    p.add_argument("--minimum-packets", type=int, default=2)
    args = p.parse_args()
    data = args.capture.read_bytes()
    try:
        result = parse_capture(data, args.minimum_packets) if args.scan else parse_packet(data)
    except ValueError as e:
        p.error(str(e))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
