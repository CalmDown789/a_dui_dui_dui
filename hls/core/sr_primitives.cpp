#include "sr_primitives.hpp"

namespace sr {

void conv3x3_mac(
    const activation_t pixels[MAX_INPUT_CHANNELS][KERNEL_SIZE][KERNEL_SIZE],
    const weight_t weights[MAX_INPUT_CHANNELS][KERNEL_SIZE][KERNEL_SIZE],
    channel_count_t input_channels,
    accumulator_t bias,
    accumulator_t &result) {
    accumulator_t sum = bias;

channel_loop:
    for (int channel = 0; channel < MAX_INPUT_CHANNELS; ++channel) {
#pragma HLS PIPELINE II=1
        if (channel < input_channels) {
        kernel_row_loop:
            for (int row = 0; row < KERNEL_SIZE; ++row) {
#pragma HLS UNROLL
            kernel_col_loop:
                for (int col = 0; col < KERNEL_SIZE; ++col) {
#pragma HLS UNROLL
                    const ap_int<16> product = pixels[channel][row][col] *
                                               weights[channel][row][col];
                    sum += product;
                }
            }
        }
    }

    result = sum;
}

activation_t saturate_int8(accumulator_t value) {
    if (value > 127) {
        return 127;
    }
    if (value < -128) {
        return -128;
    }
    return static_cast<activation_t>(value);
}

void pixel_shuffle2x_block(
    const activation_t channels[SUBPIXEL_CHANNELS],
    activation_t block[UPSCALE][UPSCALE]) {
row_loop:
    for (int row = 0; row < UPSCALE; ++row) {
    col_loop:
        for (int col = 0; col < UPSCALE; ++col) {
#pragma HLS UNROLL
            block[row][col] = channels[row * UPSCALE + col];
        }
    }
}

}  // namespace sr

void conv3x3_mac_top(
    const sr::activation_t pixels[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                                 [sr::KERNEL_SIZE],
    const sr::weight_t weights[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                              [sr::KERNEL_SIZE],
    sr::channel_count_t input_channels,
    sr::accumulator_t bias,
    sr::accumulator_t &result) {
#pragma HLS ARRAY_PARTITION variable=pixels complete dim=2
#pragma HLS ARRAY_PARTITION variable=pixels complete dim=3
#pragma HLS ARRAY_PARTITION variable=weights complete dim=2
#pragma HLS ARRAY_PARTITION variable=weights complete dim=3
#pragma HLS INTERFACE mode=ap_memory port=pixels
#pragma HLS INTERFACE mode=ap_memory port=weights
#pragma HLS INTERFACE mode=s_axilite port=input_channels bundle=control
#pragma HLS INTERFACE mode=s_axilite port=bias bundle=control
#pragma HLS INTERFACE mode=s_axilite port=result bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    sr::conv3x3_mac(pixels, weights, input_channels, bias, result);
}
