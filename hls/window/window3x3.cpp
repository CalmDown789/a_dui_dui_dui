#include "window3x3.hpp"

void window3x3_stream_top(
    hls::stream<sr::activation_t> &pixel_in,
    hls::stream<sr::window3x3_t> &window_out,
    ap_uint<16> rows,
    ap_uint<16> cols) {
#pragma HLS INTERFACE mode=axis port=pixel_in
#pragma HLS INTERFACE mode=axis port=window_out
#pragma HLS INTERFACE mode=s_axilite port=rows bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cols bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    static sr::activation_t line_buffer[2][sr::MAX_FRAME_WIDTH];
#pragma HLS ARRAY_PARTITION variable=line_buffer complete dim=1
#pragma HLS BIND_STORAGE variable=line_buffer type=ram_2p impl=bram

    sr::activation_t shift[3][sr::KERNEL_SIZE] = {};
#pragma HLS ARRAY_PARTITION variable=shift complete dim=0

row_loop:
    for (int row = 0; row < rows; ++row) {
#pragma HLS LOOP_TRIPCOUNT min=3 max=360 avg=360
    col_loop:
        for (int col = 0; col < cols; ++col) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=3 max=640 avg=640
            const sr::activation_t current = pixel_in.read();
            const sr::activation_t previous_row = line_buffer[1][col];
            const sr::activation_t previous_two_rows = line_buffer[0][col];

            line_buffer[0][col] = previous_row;
            line_buffer[1][col] = current;

        shift_rows:
            for (int wr = 0; wr < sr::KERNEL_SIZE; ++wr) {
#pragma HLS UNROLL
                shift[wr][0] = shift[wr][1];
                shift[wr][1] = shift[wr][2];
            }
            shift[0][2] = previous_two_rows;
            shift[1][2] = previous_row;
            shift[2][2] = current;

            if (row >= 2 && col >= 2) {
                sr::window3x3_t output;
            copy_rows:
                for (int wr = 0; wr < sr::KERNEL_SIZE; ++wr) {
#pragma HLS UNROLL
                copy_cols:
                    for (int wc = 0; wc < sr::KERNEL_SIZE; ++wc) {
#pragma HLS UNROLL
                        output.data[wr][wc] = shift[wr][wc];
                    }
                }
                window_out.write(output);
            }
        }
    }
}
