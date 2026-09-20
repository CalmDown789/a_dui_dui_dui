#include "conv3x3_layer.hpp"
#include "layer_vector.hpp"

#include <iostream>

namespace {

int error_count = 0;

}  // namespace

int main() {
    hls::stream<sr::activation_t> feature_stream;
    hls::stream<sr::accumulator_t> result_stream;
    sr::weight_t weights[sr::MAX_OUTPUT_CHANNELS][sr::MAX_INPUT_CHANNELS]
                        [sr::KERNEL_SIZE][sr::KERNEL_SIZE] = {};
    sr::accumulator_t bias[sr::MAX_OUTPUT_CHANNELS] = {};

    for (int out_channel = 0; out_channel < layer_vector::OUTPUT_CHANNELS;
         ++out_channel) {
        bias[out_channel] = layer_vector::BIAS[out_channel];
        for (int in_channel = 0; in_channel < layer_vector::INPUT_CHANNELS;
             ++in_channel) {
            for (int row = 0; row < sr::KERNEL_SIZE; ++row) {
                for (int col = 0; col < sr::KERNEL_SIZE; ++col) {
                    weights[out_channel][in_channel][row][col] =
                        layer_vector::WEIGHTS[out_channel][in_channel][row][col];
                }
            }
        }
    }

    for (int row = 0; row < layer_vector::ROWS; ++row) {
        for (int col = 0; col < layer_vector::COLS; ++col) {
            for (int in_channel = 0; in_channel < layer_vector::INPUT_CHANNELS;
                 ++in_channel) {
                feature_stream.write(layer_vector::INPUT[row][col][in_channel]);
            }
        }
    }

    conv3x3_layer_top(feature_stream, result_stream, weights, bias,
                      layer_vector::INPUT_CHANNELS,
                      layer_vector::OUTPUT_CHANNELS, layer_vector::ROWS,
                      layer_vector::COLS);

    int result_count = 0;
    for (int row = 0; row < layer_vector::OUTPUT_ROWS; ++row) {
        for (int col = 0; col < layer_vector::OUTPUT_COLS; ++col) {
            for (int out_channel = 0;
                 out_channel < layer_vector::OUTPUT_CHANNELS;
                 ++out_channel) {
                if (result_stream.empty()) {
                    std::cerr << "FAIL missing output" << std::endl;
                    ++error_count;
                    continue;
                }
                const int actual = result_stream.read().to_int();
                const int expected = layer_vector::EXPECTED[row][col][out_channel];
                if (actual != expected) {
                    std::cerr << "FAIL output(row=" << row << ',' << col
                              << ", channel=" << out_channel << "): expected "
                              << expected << ", got " << actual << std::endl;
                    ++error_count;
                }
                ++result_count;
            }
        }
    }

    if (!result_stream.empty()) {
        std::cerr << "FAIL unexpected extra output" << std::endl;
        ++error_count;
    }
    const int expected_count = layer_vector::OUTPUT_ROWS *
                               layer_vector::OUTPUT_COLS *
                               layer_vector::OUTPUT_CHANNELS;
    if (result_count != expected_count) {
        std::cerr << "FAIL expected " << expected_count << " results, got "
                  << result_count << std::endl;
        ++error_count;
    }

    if (error_count != 0) {
        std::cerr << "CONV3X3_LAYER_TEST_FAIL errors=" << error_count << std::endl;
        return 1;
    }

    std::cout << "CONV3X3_LAYER_TEST_PASS results=" << result_count << std::endl;
    return 0;
}
