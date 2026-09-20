#include "sr_primitives.hpp"

#include <iostream>

namespace {

int error_count = 0;

void expect_equal(const char *name, int actual, int expected) {
    if (actual != expected) {
        std::cerr << "FAIL " << name << ": expected " << expected
                  << ", got " << actual << std::endl;
        ++error_count;
    }
}

}  // namespace

int main() {
    sr::activation_t pixels[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                           [sr::KERNEL_SIZE] = {};
    sr::weight_t weights[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                        [sr::KERNEL_SIZE] = {};

    // Channel 0 contributes 1+2+...+9 = 45.
    int value = 1;
    for (int row = 0; row < sr::KERNEL_SIZE; ++row) {
        for (int col = 0; col < sr::KERNEL_SIZE; ++col) {
            pixels[0][row][col] = value++;
            weights[0][row][col] = 1;
        }
    }

    // Channel 1 contributes nine products of 2*(-1) = -18.
    for (int row = 0; row < sr::KERNEL_SIZE; ++row) {
        for (int col = 0; col < sr::KERNEL_SIZE; ++col) {
            pixels[1][row][col] = 2;
            weights[1][row][col] = -1;
        }
    }

    sr::accumulator_t result = 0;
    sr::conv3x3_mac(pixels, weights, 1, 7, result);
    expect_equal("one_channel_with_bias", result.to_int(), 52);

    sr::conv3x3_mac(pixels, weights, 2, 7, result);
    expect_equal("two_channels_signed", result.to_int(), 34);

    sr::conv3x3_mac(pixels, weights, 0, -11, result);
    expect_equal("zero_channels_bias_only", result.to_int(), -11);

    expect_equal("saturate_high", sr::saturate_int8(200).to_int(), 127);
    expect_equal("saturate_low", sr::saturate_int8(-200).to_int(), -128);
    expect_equal("saturate_passthrough", sr::saturate_int8(-17).to_int(), -17);

    const sr::activation_t subpixels[sr::SUBPIXEL_CHANNELS] = {10, 20, 30, 40};
    sr::activation_t block[sr::UPSCALE][sr::UPSCALE] = {};
    sr::pixel_shuffle2x_block(subpixels, block);
    expect_equal("shuffle_00", block[0][0].to_int(), 10);
    expect_equal("shuffle_01", block[0][1].to_int(), 20);
    expect_equal("shuffle_10", block[1][0].to_int(), 30);
    expect_equal("shuffle_11", block[1][1].to_int(), 40);

    if (error_count != 0) {
        std::cerr << "SR_PRIMITIVES_TEST_FAIL errors=" << error_count << std::endl;
        return 1;
    }

    std::cout << "SR_PRIMITIVES_TEST_PASS" << std::endl;
    return 0;
}
