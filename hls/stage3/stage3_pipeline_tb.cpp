#include "stage3_pipeline.hpp"

#include <iostream>

namespace {

constexpr int ROWS = 4;
constexpr int COLS = 5;
constexpr int INPUT_CHANNELS = 2;

int error_count = 0;

void push_input(hls::stream<sr::activation_t> &feature_stream) {
    for (int row = 0; row < ROWS; ++row) {
        for (int col = 0; col < COLS; ++col) {
            feature_stream.write(row * COLS + col + 1);
            feature_stream.write(-2);
        }
    }
}

void check_output(hls::stream<sr::activation_t> &pixel_stream,
                  bool use_nonzero_weights) {
    constexpr int HIGH_ROWS = (ROWS - 2) * 2;
    constexpr int HIGH_COLS = (COLS - 2) * 2;

    for (int row = 0; row < HIGH_ROWS; ++row) {
        for (int col = 0; col < HIGH_COLS; ++col) {
            if (pixel_stream.empty()) {
                std::cerr << "FAIL missing pixel at " << row << ',' << col
                          << std::endl;
                ++error_count;
                continue;
            }

            const int subpixel_channel = (row % 2) * 2 + (col % 2);
            int expected = (subpixel_channel + 1) * 10;
            if (use_nonzero_weights) {
                const int low_row = row / 2;
                const int low_col = col / 2;
                const int center_value = low_row * COLS + low_col + 7;
                expected = (subpixel_channel + 1) * center_value -
                           subpixel_channel;
            }

            const int actual = pixel_stream.read().to_int();
            if (actual != expected) {
                std::cerr << "FAIL pixel(" << row << ',' << col
                          << "): expected " << expected << ", got " << actual
                          << std::endl;
                ++error_count;
            }
        }
    }

    if (!pixel_stream.empty()) {
        std::cerr << "FAIL unexpected extra output" << std::endl;
        ++error_count;
    }
}

void run_case(bool use_nonzero_weights) {
    hls::stream<sr::activation_t> feature_stream;
    hls::stream<sr::activation_t> pixel_stream;

    sr::weight_t weights[sr::MAX_OUTPUT_CHANNELS][sr::MAX_INPUT_CHANNELS]
                        [sr::KERNEL_SIZE][sr::KERNEL_SIZE] = {};
    sr::accumulator_t bias[sr::MAX_OUTPUT_CHANNELS] = {};
    sr::scale_t requant_multiplier[sr::POST_MAX_CHANNELS] = {};
    sr::shift_t requant_shift[sr::POST_MAX_CHANNELS] = {};
    sr::zero_point_t output_zero_point[sr::POST_MAX_CHANNELS] = {};

    for (int channel = 0; channel < 4; ++channel) {
        bias[channel] = use_nonzero_weights ? -3 * channel : (channel + 1) * 10;
        requant_multiplier[channel] = 1;
        requant_shift[channel] = 0;
        if (use_nonzero_weights) {
            weights[channel][0][1][1] = channel + 1;
            weights[channel][1][1][1] = -channel;
        }
    }

    push_input(feature_stream);

    stage3_pipeline_top(
        feature_stream, pixel_stream, weights, bias, requant_multiplier,
        requant_shift, output_zero_point, INPUT_CHANNELS, ROWS, COLS,
        sr::ROUND_TOWARD_ZERO, 1, 0, 1, 2, 3);

    check_output(pixel_stream, use_nonzero_weights);
}

}  // namespace

int main() {
    run_case(false);
    run_case(true);

    if (error_count != 0) {
        std::cerr << "STAGE3_PIPELINE_TEST_FAIL errors=" << error_count
                  << std::endl;
        return 1;
    }

    std::cout << "STAGE3_PIPELINE_TEST_PASS cases=2 pixels_per_case=24"
              << std::endl;
    return 0;
}
