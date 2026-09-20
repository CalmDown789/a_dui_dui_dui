#ifndef WINDOW3X3_HPP
#define WINDOW3X3_HPP

#include <ap_int.h>
#include <hls_stream.h>

#include "sr_types.hpp"

namespace sr {

constexpr int MAX_FRAME_WIDTH = 640;

struct window3x3_t {
    activation_t data[KERNEL_SIZE][KERNEL_SIZE];
};

}  // namespace sr

// Emits one complete 3x3 window for every input position with row>=2 and
// col>=2. Border policy is intentionally handled outside this primitive.
void window3x3_stream_top(
    hls::stream<sr::activation_t> &pixel_in,
    hls::stream<sr::window3x3_t> &window_out,
    ap_uint<16> rows,
    ap_uint<16> cols);

#endif
