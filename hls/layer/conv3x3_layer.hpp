#ifndef CONV3X3_LAYER_HPP
#define CONV3X3_LAYER_HPP

#include <ap_int.h>
#include <hls_stream.h>

#include "sr_types.hpp"

namespace sr {

constexpr int MAX_OUTPUT_CHANNELS = 16;
constexpr int LAYER_MAX_FRAME_WIDTH = 640;

}  // namespace sr

// Input stream order:  row -> column -> input_channel.
// Output stream order: row -> column -> output_channel.
// Only complete 3x3 windows are emitted; border adaptation is external.
void conv3x3_layer_top(
    hls::stream<sr::activation_t> &feature_in,
    hls::stream<sr::accumulator_t> &conv_out,
    const sr::weight_t weights[sr::MAX_OUTPUT_CHANNELS]
                              [sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                              [sr::KERNEL_SIZE],
    const sr::accumulator_t bias[sr::MAX_OUTPUT_CHANNELS],
    sr::channel_count_t input_channels,
    sr::channel_count_t output_channels,
    ap_uint<16> rows,
    ap_uint<16> cols);

#endif
