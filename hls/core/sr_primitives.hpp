#ifndef SR_PRIMITIVES_HPP
#define SR_PRIMITIVES_HPP

#include "sr_types.hpp"

namespace sr {

// Arithmetic backend for one output channel at one spatial position.
// Padding, line buffering and output quantization are deliberately outside
// this primitive because those rules still require team confirmation.
void conv3x3_mac(
    const activation_t pixels[MAX_INPUT_CHANNELS][KERNEL_SIZE][KERNEL_SIZE],
    const weight_t weights[MAX_INPUT_CHANNELS][KERNEL_SIZE][KERNEL_SIZE],
    channel_count_t input_channels,
    accumulator_t bias,
    accumulator_t &result);

activation_t saturate_int8(accumulator_t value);

// Candidate x2 pixel-shuffle order. The final channel order must be checked
// against member B's exported model before the interface is frozen.
void pixel_shuffle2x_block(
    const activation_t channels[SUBPIXEL_CHANNELS],
    activation_t block[UPSCALE][UPSCALE]);

}  // namespace sr

// Vitis HLS 2025.2 does not accept a namespace-qualified function as the Tcl
// top name, so synthesis uses this thin global wrapper.
void conv3x3_mac_top(
    const sr::activation_t pixels[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                                 [sr::KERNEL_SIZE],
    const sr::weight_t weights[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                              [sr::KERNEL_SIZE],
    sr::channel_count_t input_channels,
    sr::accumulator_t bias,
    sr::accumulator_t &result);

#endif
