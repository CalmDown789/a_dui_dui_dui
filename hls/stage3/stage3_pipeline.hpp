#ifndef STAGE3_PIPELINE_HPP
#define STAGE3_PIPELINE_HPP

#include <ap_int.h>
#include <hls_stream.h>

#include "conv3x3_layer.hpp"
#include "pixel_shuffle.hpp"
#include "postprocess.hpp"

void stage3_pipeline_top(
    hls::stream<sr::activation_t> &feature_in,
    hls::stream<sr::activation_t> &pixel_out,
    const sr::weight_t weights[sr::MAX_OUTPUT_CHANNELS]
                              [sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                              [sr::KERNEL_SIZE],
    const sr::accumulator_t bias[sr::MAX_OUTPUT_CHANNELS],
    const sr::scale_t requant_multiplier[sr::POST_MAX_CHANNELS],
    const sr::shift_t requant_shift[sr::POST_MAX_CHANNELS],
    const sr::zero_point_t output_zero_point[sr::POST_MAX_CHANNELS],
    sr::channel_count_t input_channels,
    ap_uint<16> rows,
    ap_uint<16> cols,
    ap_uint<2> rounding_mode,
    ap_uint<1> enable_saturation,
    ap_uint<2> map00,
    ap_uint<2> map01,
    ap_uint<2> map10,
    ap_uint<2> map11);

#endif
