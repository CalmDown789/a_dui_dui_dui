#ifndef POSTPROCESS_HPP
#define POSTPROCESS_HPP

#include <ap_int.h>
#include <hls_stream.h>

#include "sr_types.hpp"

namespace sr {

constexpr int POST_MAX_CHANNELS = 16;

enum rounding_mode_t : unsigned {
    ROUND_NEAREST_AWAY = 0,
    ROUND_TOWARD_ZERO = 1,
    ROUND_FLOOR = 2,
};

using scale_t = ap_int<32>;
using shift_t = ap_uint<6>;
using zero_point_t = ap_int<16>;

}  // namespace sr

// Stream order on both sides: spatial_position -> output_channel.
void postprocess_stream_top(
    hls::stream<sr::accumulator_t> &acc_in,
    hls::stream<sr::activation_t> &activation_out,
    const sr::scale_t requant_multiplier[sr::POST_MAX_CHANNELS],
    const sr::shift_t requant_shift[sr::POST_MAX_CHANNELS],
    const sr::zero_point_t output_zero_point[sr::POST_MAX_CHANNELS],
    const sr::scale_t prelu_multiplier[sr::POST_MAX_CHANNELS],
    const sr::shift_t prelu_shift[sr::POST_MAX_CHANNELS],
    ap_uint<32> spatial_positions,
    sr::channel_count_t output_channels,
    ap_uint<2> rounding_mode,
    ap_uint<1> enable_prelu,
    ap_uint<1> prelu_before_requant,
    ap_uint<1> enable_saturation);

#endif
