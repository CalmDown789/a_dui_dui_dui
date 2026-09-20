#include "window3x3.hpp"

#include <iostream>

namespace {

constexpr int ROWS = 4;
constexpr int COLS = 5;

int error_count = 0;

void check_window(const sr::window3x3_t &window, int bottom_row, int right_col) {
    for (int wr = 0; wr < sr::KERNEL_SIZE; ++wr) {
        for (int wc = 0; wc < sr::KERNEL_SIZE; ++wc) {
            const int source_row = bottom_row - 2 + wr;
            const int source_col = right_col - 2 + wc;
            const int expected = source_row * COLS + source_col + 1;
            const int actual = window.data[wr][wc].to_int();
            if (actual != expected) {
                std::cerr << "FAIL window(bottom=" << bottom_row << ',' << right_col
                          << ") [" << wr << "][" << wc << "]: expected "
                          << expected << ", got " << actual << std::endl;
                ++error_count;
            }
        }
    }
}

}  // namespace

int main() {
    hls::stream<sr::activation_t> pixel_stream;
    hls::stream<sr::window3x3_t> window_stream;

    for (int value = 1; value <= ROWS * COLS; ++value) {
        pixel_stream.write(value);
    }

    window3x3_stream_top(pixel_stream, window_stream, ROWS, COLS);

    int window_count = 0;
    for (int row = 2; row < ROWS; ++row) {
        for (int col = 2; col < COLS; ++col) {
            if (window_stream.empty()) {
                std::cerr << "FAIL missing window at bottom=" << row
                          << ", right=" << col << std::endl;
                ++error_count;
                continue;
            }
            check_window(window_stream.read(), row, col);
            ++window_count;
        }
    }

    if (!window_stream.empty()) {
        std::cerr << "FAIL unexpected extra window" << std::endl;
        ++error_count;
    }

    if (window_count != (ROWS - 2) * (COLS - 2)) {
        std::cerr << "FAIL expected 6 windows, got " << window_count << std::endl;
        ++error_count;
    }

    if (error_count != 0) {
        std::cerr << "WINDOW3X3_HLS_TEST_FAIL errors=" << error_count << std::endl;
        return 1;
    }

    std::cout << "WINDOW3X3_HLS_TEST_PASS windows=" << window_count << std::endl;
    return 0;
}
