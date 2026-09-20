#include "postprocess.hpp"

#include <iostream>

namespace {

int error_count = 0;

void expect_stream(hls::stream<sr::activation_t> &stream, const int *expected,
                   int count, const char *test_name) {
    for (int index = 0; index < count; ++index) {
        if (stream.empty()) {
            std::cerr << "FAIL " << test_name << " missing index " << index
                      << std::endl;
            ++error_count;
            continue;
        }
        const int actual = stream.read().to_int();
        if (actual != expected[index]) {
            std::cerr << "FAIL " << test_name << " index " << index
                      << ": expected " << expected[index] << ", got " << actual
                      << std::endl;
            ++error_count;
        }
    }
    if (!stream.empty()) {
        std::cerr << "FAIL " << test_name << " unexpected extra output"
                  << std::endl;
        ++error_count;
    }
}

}  // namespace

int main() {
    sr::scale_t requant_multiplier[sr::POST_MAX_CHANNELS] = {};
    sr::shift_t requant_shift[sr::POST_MAX_CHANNELS] = {};
    sr::zero_point_t output_zero_point[sr::POST_MAX_CHANNELS] = {};
    sr::scale_t prelu_multiplier[sr::POST_MAX_CHANNELS] = {};
    sr::shift_t prelu_shift[sr::POST_MAX_CHANNELS] = {};

    for (int channel = 0; channel < 3; ++channel) {
        requant_multiplier[channel] = 1;
        requant_shift[channel] = 1;
        prelu_multiplier[channel] = 1;
        prelu_shift[channel] = 1;
    }

    hls::stream<sr::accumulator_t> input_a;
    hls::stream<sr::activation_t> output_a;
    const int values_a[6] = {-8, -3, 300, 8, 3, -300};
    for (int value : values_a) {
        input_a.write(value);
    }
    postprocess_stream_top(input_a, output_a, requant_multiplier, requant_shift,
                           output_zero_point, prelu_multiplier, prelu_shift, 2,
                           3, sr::ROUND_TOWARD_ZERO, 1, 1, 1);
    const int expected_a[6] = {-2, 0, 127, 4, 1, -75};
    expect_stream(output_a, expected_a, 6, "prelu_before_toward_zero");

    hls::stream<sr::accumulator_t> input_b;
    hls::stream<sr::activation_t> output_b;
    const int values_b[3] = {-3, 3, 255};
    for (int value : values_b) {
        input_b.write(value);
    }
    postprocess_stream_top(input_b, output_b, requant_multiplier, requant_shift,
                           output_zero_point, prelu_multiplier, prelu_shift, 1,
                           3, sr::ROUND_NEAREST_AWAY, 0, 0, 1);
    const int expected_b[3] = {-2, 2, 127};
    expect_stream(output_b, expected_b, 3, "nearest_no_prelu");

    if (error_count != 0) {
        std::cerr << "POSTPROCESS_TEST_FAIL errors=" << error_count << std::endl;
        return 1;
    }

    std::cout << "POSTPROCESS_TEST_PASS tests=2" << std::endl;
    return 0;
}
