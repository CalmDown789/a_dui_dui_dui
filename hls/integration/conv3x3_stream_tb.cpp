#include "conv3x3_stream.hpp"

#include <iostream>

namespace {

constexpr int ROWS = 4;
constexpr int COLS = 5;
constexpr int CHANNELS = 2;
constexpr int BIAS = 7;

int error_count = 0;

int channel0_value(int row, int col) {
    return row * COLS + col + 1;
}

int expected_window_sum(int bottom_row, int right_col) {
    int sum = BIAS;
    for (int wr = 0; wr < sr::KERNEL_SIZE; ++wr) {
        for (int wc = 0; wc < sr::KERNEL_SIZE; ++wc) {
            const int row = bottom_row - 2 + wr;
            const int col = right_col - 2 + wc;
            sum += channel0_value(row, col);
            sum -= 2;
        }
    }
    return sum;
}

}  // namespace

int main() {
    hls::stream<sr::activation_t> feature_stream;
    hls::stream<sr::accumulator_t> result_stream;
    sr::weight_t weights[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                        [sr::KERNEL_SIZE] = {};

    for (int row = 0; row < sr::KERNEL_SIZE; ++row) {
        for (int col = 0; col < sr::KERNEL_SIZE; ++col) {
            weights[0][row][col] = 1;
            weights[1][row][col] = -1;
        }
    }

    for (int row = 0; row < ROWS; ++row) {
        for (int col = 0; col < COLS; ++col) {
            feature_stream.write(channel0_value(row, col));
            feature_stream.write(2);
        }
    }

    conv3x3_stream_top(feature_stream, result_stream, weights, CHANNELS, BIAS,
                       ROWS, COLS);

    int result_count = 0;
    for (int row = 2; row < ROWS; ++row) {
        for (int col = 2; col < COLS; ++col) {
            if (result_stream.empty()) {
                std::cerr << "FAIL missing result at bottom=" << row
                          << ", right=" << col << std::endl;
                ++error_count;
                continue;
            }
            const int actual = result_stream.read().to_int();
            const int expected = expected_window_sum(row, col);
            if (actual != expected) {
                std::cerr << "FAIL result(bottom=" << row << ',' << col
                          << "): expected " << expected << ", got " << actual
                          << std::endl;
                ++error_count;
            }
            ++result_count;
        }
    }

    if (!result_stream.empty()) {
        std::cerr << "FAIL unexpected extra result" << std::endl;
        ++error_count;
    }
    if (result_count != 6) {
        std::cerr << "FAIL expected 6 results, got " << result_count << std::endl;
        ++error_count;
    }

    if (error_count != 0) {
        std::cerr << "CONV3X3_STREAM_TEST_FAIL errors=" << error_count << std::endl;
        return 1;
    }

    std::cout << "CONV3X3_STREAM_TEST_PASS results=" << result_count << std::endl;
    return 0;
}
