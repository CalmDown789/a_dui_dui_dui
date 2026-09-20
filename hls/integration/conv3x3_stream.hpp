#ifndef CONV3X3_STREAM_HPP
#define CONV3X3_STREAM_HPP

#include <ap_int.h>
#include <hls_stream.h>

#include "sr_types.hpp"

namespace sr {

constexpr int INTEGRATION_MAX_FRAME_WIDTH = 640;

}  // namespace sr

// Input order: row, column, input channel. For each spatial position the
// stream contains input_channels consecutive INT8 activations.
// Output: one INT32 result for each complete 3x3 window.
void conv3x3_stream_top(
    hls::stream<sr::activation_t> &feature_in,
    hls::stream<sr::accumulator_t> &conv_out,
    const sr::weight_t weights[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                              [sr::KERNEL_SIZE],
    sr::channel_count_t input_channels,
    sr::accumulator_t bias,
    ap_uint<16> rows,
    ap_uint<16> cols);

#endif
