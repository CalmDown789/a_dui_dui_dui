#include "stage3_pipeline.hpp"

namespace {

const sr::scale_t DISABLED_PRELU_MULTIPLIER[sr::POST_MAX_CHANNELS] = {};
const sr::shift_t DISABLED_PRELU_SHIFT[sr::POST_MAX_CHANNELS] = {};

void stage3_dataflow(
    hls::stream<sr::activation_t> &feature_in,
    hls::stream<sr::activation_t> &pixel_out,
    const sr::weight_t weights[sr::MAX_OUTPUT_CHANNELS]
                              [sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE]
                              [sr::KERNEL_SIZE],
    const sr::accumulator_t bias[sr::MAX_OUTPUT_CHANNELS],
    const sr::scale_t requant_multiplier[sr::POST_MAX_CHANNELS],
    const sr::shift_t requant_shift[sr::POST_MAX_CHANNELS],
    const sr::zero_point_t output_zero_point[sr::POST_MAX_CHANNELS],
    const sr::scale_t disabled_prelu_multiplier[sr::POST_MAX_CHANNELS],
    const sr::shift_t disabled_prelu_shift[sr::POST_MAX_CHANNELS],
    sr::channel_count_t input_channels,
    ap_uint<16> rows,
    ap_uint<16> cols,
    ap_uint<16> output_rows,
    ap_uint<16> output_cols,
    ap_uint<32> spatial_positions,
    ap_uint<2> rounding_mode,
    ap_uint<1> enable_saturation,
    ap_uint<2> map00,
    ap_uint<2> map01,
    ap_uint<2> map10,
    ap_uint<2> map11) {
#pragma HLS INLINE off

    hls::stream<sr::accumulator_t> accumulator_stream("accumulator_stream");
    hls::stream<sr::activation_t> channel_stream("channel_stream");
#pragma HLS STREAM variable=accumulator_stream depth=64
#pragma HLS STREAM variable=channel_stream depth=64
#pragma HLS DATAFLOW

    conv3x3_layer_top(feature_in, accumulator_stream, weights, bias,
                      input_channels, 4, rows, cols);

    postprocess_stream_top(
        accumulator_stream, channel_stream, requant_multiplier, requant_shift,
        output_zero_point, disabled_prelu_multiplier, disabled_prelu_shift,
        spatial_positions, 4, rounding_mode, 0, 0, enable_saturation);

    pixel_shuffle2x_stream_top(channel_stream, pixel_out, output_rows,
                               output_cols, map00, map01, map10, map11);
}

}  // namespace

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
    ap_uint<2> map11) {
#pragma HLS INTERFACE mode=axis port=feature_in
#pragma HLS INTERFACE mode=axis port=pixel_out
#pragma HLS INTERFACE mode=ap_memory port=weights
#pragma HLS INTERFACE mode=ap_memory port=bias
#pragma HLS INTERFACE mode=ap_memory port=requant_multiplier
#pragma HLS INTERFACE mode=ap_memory port=requant_shift
#pragma HLS INTERFACE mode=ap_memory port=output_zero_point
#pragma HLS INTERFACE mode=s_axilite port=input_channels bundle=control
#pragma HLS INTERFACE mode=s_axilite port=rows bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cols bundle=control
#pragma HLS INTERFACE mode=s_axilite port=rounding_mode bundle=control
#pragma HLS INTERFACE mode=s_axilite port=enable_saturation bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map00 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map01 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map10 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map11 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    if (rows < 3 || cols < 3 || input_channels == 0) {
        return;
    }

    const ap_uint<16> output_rows = rows - 2;
    const ap_uint<16> output_cols = cols - 2;
    const ap_uint<32> spatial_positions = output_rows * output_cols;

    stage3_dataflow(
        feature_in, pixel_out, weights, bias, requant_multiplier, requant_shift,
        output_zero_point, DISABLED_PRELU_MULTIPLIER, DISABLED_PRELU_SHIFT,
        input_channels, rows, cols, output_rows, output_cols, spatial_positions,
        rounding_mode, enable_saturation, map00, map01, map10, map11);
}
