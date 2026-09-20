#include "conv3x3_layer.hpp"

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
    ap_uint<16> cols) {
#pragma HLS INTERFACE mode=axis port=feature_in
#pragma HLS INTERFACE mode=axis port=conv_out
#pragma HLS INTERFACE mode=ap_memory port=weights
#pragma HLS INTERFACE mode=ap_memory port=bias
#pragma HLS INTERFACE mode=s_axilite port=input_channels bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output_channels bundle=control
#pragma HLS INTERFACE mode=s_axilite port=rows bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cols bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

#pragma HLS ARRAY_PARTITION variable=weights complete dim=3
#pragma HLS ARRAY_PARTITION variable=weights complete dim=4

    static sr::activation_t
        line_buffer[sr::MAX_INPUT_CHANNELS][2][sr::LAYER_MAX_FRAME_WIDTH];
#pragma HLS ARRAY_PARTITION variable=line_buffer complete dim=2
#pragma HLS BIND_STORAGE variable=line_buffer type=ram_2p impl=bram

    sr::activation_t
        shift[sr::MAX_INPUT_CHANNELS][sr::KERNEL_SIZE][sr::KERNEL_SIZE] = {};
#pragma HLS ARRAY_PARTITION variable=shift complete dim=2
#pragma HLS ARRAY_PARTITION variable=shift complete dim=3

    sr::accumulator_t accumulators[sr::MAX_OUTPUT_CHANNELS];
#pragma HLS ARRAY_PARTITION variable=accumulators complete dim=1

row_loop:
    for (int row = 0; row < rows; ++row) {
#pragma HLS LOOP_TRIPCOUNT min=3 max=360 avg=360
    col_loop:
        for (int col = 0; col < cols; ++col) {
#pragma HLS LOOP_TRIPCOUNT min=3 max=640 avg=640
        init_output_loop:
            for (int out_channel = 0; out_channel < output_channels; ++out_channel) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=16 avg=8
                accumulators[out_channel] = bias[out_channel];
            }

        input_channel_loop:
            for (int in_channel = 0; in_channel < input_channels; ++in_channel) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16 avg=8
                const sr::activation_t current = feature_in.read();
                const sr::activation_t previous_row =
                    line_buffer[in_channel][1][col];
                const sr::activation_t previous_two_rows =
                    line_buffer[in_channel][0][col];

                line_buffer[in_channel][0][col] = previous_row;
                line_buffer[in_channel][1][col] = current;

                shift[in_channel][0][0] = shift[in_channel][0][1];
                shift[in_channel][0][1] = shift[in_channel][0][2];
                shift[in_channel][0][2] = previous_two_rows;
                shift[in_channel][1][0] = shift[in_channel][1][1];
                shift[in_channel][1][1] = shift[in_channel][1][2];
                shift[in_channel][1][2] = previous_row;
                shift[in_channel][2][0] = shift[in_channel][2][1];
                shift[in_channel][2][1] = shift[in_channel][2][2];
                shift[in_channel][2][2] = current;

            output_channel_loop:
                for (int out_channel = 0; out_channel < output_channels;
                     ++out_channel) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=16 avg=8
                    if (row >= 2 && col >= 2) {
                        sr::accumulator_t dot = 0;
                    kernel_row_loop:
                        for (int kernel_row = 0; kernel_row < sr::KERNEL_SIZE;
                             ++kernel_row) {
#pragma HLS UNROLL
                        kernel_col_loop:
                            for (int kernel_col = 0;
                                 kernel_col < sr::KERNEL_SIZE; ++kernel_col) {
#pragma HLS UNROLL
                                const ap_int<16> product =
                                    shift[in_channel][kernel_row][kernel_col] *
                                    weights[out_channel][in_channel][kernel_row]
                                           [kernel_col];
                                dot += product;
                            }
                        }
                        accumulators[out_channel] += dot;
                    }
                }
            }

            if (row >= 2 && col >= 2) {
            write_output_loop:
                for (int out_channel = 0; out_channel < output_channels;
                     ++out_channel) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=16 avg=8
                    conv_out.write(accumulators[out_channel]);
                }
            }
        }
    }
}
