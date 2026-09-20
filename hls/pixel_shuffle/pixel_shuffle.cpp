#include "pixel_shuffle.hpp"

namespace {

sr::activation_t select_channel(ap_uint<2> index, sr::activation_t channel0,
                                sr::activation_t channel1,
                                sr::activation_t channel2,
                                sr::activation_t channel3) {
#pragma HLS INLINE
    switch (index) {
        case 0:
            return channel0;
        case 1:
            return channel1;
        case 2:
            return channel2;
        default:
            return channel3;
    }
}

}  // namespace

void pixel_shuffle2x_stream_top(
    hls::stream<sr::activation_t> &channels_in,
    hls::stream<sr::activation_t> &pixel_out,
    ap_uint<16> rows,
    ap_uint<16> cols,
    ap_uint<2> map00,
    ap_uint<2> map01,
    ap_uint<2> map10,
    ap_uint<2> map11) {
#pragma HLS INTERFACE mode=axis port=channels_in
#pragma HLS INTERFACE mode=axis port=pixel_out
#pragma HLS INTERFACE mode=s_axilite port=rows bundle=control
#pragma HLS INTERFACE mode=s_axilite port=cols bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map00 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map01 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map10 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=map11 bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

    static sr::activation_t lower_row[sr::PIXEL_SHUFFLE_MAX_WIDTH][2];
#pragma HLS ARRAY_PARTITION variable=lower_row complete dim=2
#pragma HLS BIND_STORAGE variable=lower_row type=ram_2p impl=bram

low_row_loop:
    for (int row = 0; row < rows; ++row) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=360 avg=360
    produce_upper_row:
        for (int col = 0; col < cols; ++col) {
#pragma HLS PIPELINE II=4
#pragma HLS LOOP_TRIPCOUNT min=1 max=640 avg=640
            const sr::activation_t channel0 = channels_in.read();
            const sr::activation_t channel1 = channels_in.read();
            const sr::activation_t channel2 = channels_in.read();
            const sr::activation_t channel3 = channels_in.read();

            pixel_out.write(
                select_channel(map00, channel0, channel1, channel2, channel3));
            pixel_out.write(
                select_channel(map01, channel0, channel1, channel2, channel3));
            lower_row[col][0] =
                select_channel(map10, channel0, channel1, channel2, channel3);
            lower_row[col][1] =
                select_channel(map11, channel0, channel1, channel2, channel3);
        }

    produce_lower_row:
        for (int col = 0; col < cols; ++col) {
#pragma HLS PIPELINE II=2
#pragma HLS LOOP_TRIPCOUNT min=1 max=640 avg=640
            pixel_out.write(lower_row[col][0]);
            pixel_out.write(lower_row[col][1]);
        }
    }
}
