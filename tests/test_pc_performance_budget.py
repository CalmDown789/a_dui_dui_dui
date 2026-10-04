from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/pc_performance_budget.py"
spec = importlib.util.spec_from_file_location("pc_performance_budget", FILE)
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


def test_current_gray_30fps_budget_matches_reference_arithmetic():
    result = budget.calculate_case(960, 540, 2, 30, "Y8", 921600, 10, 1000)
    assert result["input_bytes_per_frame"] == 518_400
    assert result["output_bytes_per_frame"] == 2_073_600
    assert result["input_payload_MB_s"] == 15.552
    assert result["output_payload_MB_s"] == 62.208
    assert result["aggregate_payload_MB_s"] == 77.76
    assert abs(result["uart_input_seconds_per_frame_including_20B_header"] - 5.625217013888889) < 1e-12
    assert result["uart_output_seconds_per_frame"] == 22.5
    assert result["uart_stop_and_wait_max_fps_ideal"] < 0.036
    assert result["combined_one_pair_buffers_MB"] == 2.592
    assert result["display_active_rgb24_payload_Gbps"] == 1.492992


def test_alternative_formats_and_dimension_validation():
    yuv = budget.calculate_case(960, 540, 2, 30, "YUV420P", 921600, 10, 1000)
    rgb = budget.calculate_case(960, 540, 2, 30, "RGB24", 921600, 10, 1000)
    assert yuv["input_bytes_per_frame"] == 777_600
    assert yuv["output_bytes_per_frame"] == 3_110_400
    assert rgb["input_bytes_per_frame"] == 1_555_200
    assert rgb["output_bytes_per_frame"] == 6_220_800
    try:
        budget.frame_bytes(959, 539, "YUV420P")
    except ValueError as error:
        assert "even" in str(error)
    else:
        raise AssertionError("odd YUV420P dimensions must be rejected")
