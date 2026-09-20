#ifndef PIXEL_SHUFFLE_HPP
#define PIXEL_SHUFFLE_HPP

#include <ap_int.h>
#include <hls_stream.h>

#include "sr_types.hpp"

namespace sr {

constexpr int PIXEL_SHUFFLE_MAX_WIDTH = 640;

}  // namespace sr

// Input order: low_row -> low_col -> channel(4 values).
// Output order: ordinary raster scan of the 2x enlarged single-channel image.
// map00/map01/map10/map11 select the source channel for each 2x2 position.
void pixel_shuffle2x_stream_top(
    hls::stream<sr::activation_t> &channels_in,
    hls::stream<sr::activation_t> &pixel_out,
    ap_uint<16> rows,
    ap_uint<16> cols,
    ap_uint<2> map00,
    ap_uint<2> map01,
    ap_uint<2> map10,
    ap_uint<2> map11);

#endif
