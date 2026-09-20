#include "pixel_shuffle.hpp"

#include <iostream>

namespace {

constexpr int ROWS = 2;
constexpr int COLS = 3;

int error_count = 0;

int source_value(int row, int col, int channel) {
    return row * 100 + col * 10 + channel;
}

void run_case(const int map[4], const char *name) {
    hls::stream<sr::activation_t> input_stream;
    hls::stream<sr::activation_t> output_stream;

    for (int row = 0; row < ROWS; ++row) {
        for (int col = 0; col < COLS; ++col) {
            for (int channel = 0; channel < 4; ++channel) {
                input_stream.write(source_value(row, col, channel));
            }
        }
    }

    pixel_shuffle2x_stream_top(input_stream, output_stream, ROWS, COLS, map[0],
                               map[1], map[2], map[3]);

    for (int high_row = 0; high_row < ROWS * 2; ++high_row) {
        for (int high_col = 0; high_col < COLS * 2; ++high_col) {
            if (output_stream.empty()) {
                std::cerr << "FAIL " << name << " missing pixel" << std::endl;
                ++error_count;
                continue;
            }
            const int low_row = high_row / 2;
            const int low_col = high_col / 2;
            const int offset = (high_row % 2) * 2 + (high_col % 2);
            const int expected = source_value(low_row, low_col, map[offset]);
            const int actual = output_stream.read().to_int();
            if (actual != expected) {
                std::cerr << "FAIL " << name << " pixel(" << high_row << ','
                          << high_col << "): expected " << expected << ", got "
                          << actual << std::endl;
                ++error_count;
            }
        }
    }

    if (!output_stream.empty()) {
        std::cerr << "FAIL " << name << " unexpected extra output" << std::endl;
        ++error_count;
    }
}

}  // namespace

int main() {
    const int standard_map[4] = {0, 1, 2, 3};
    const int swapped_map[4] = {3, 2, 1, 0};
    run_case(standard_map, "standard_map");
    run_case(swapped_map, "swapped_map");

    if (error_count != 0) {
        std::cerr << "PIXEL_SHUFFLE_TEST_FAIL errors=" << error_count << std::endl;
        return 1;
    }

    std::cout << "PIXEL_SHUFFLE_TEST_PASS cases=2" << std::endl;
    return 0;
}
