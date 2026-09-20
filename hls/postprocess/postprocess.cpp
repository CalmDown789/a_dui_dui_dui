#include "postprocess.hpp"

namespace {

ap_int<64> rounded_shift(ap_int<64> value, sr::shift_t shift,
                         ap_uint<2> rounding_mode) {
#pragma HLS INLINE
    if (shift == 0) {
        return value;
    }

    if (rounding_mode == sr::ROUND_FLOOR) {
        return value >> shift;
    }

    const bool negative = value < 0;
    ap_uint<64> magnitude = negative ? ap_uint<64>(-value) : ap_uint<64>(value);
    if (rounding_mode == sr::ROUND_NEAREST_AWAY) {
        magnitude += ap_uint<64>(1) << (shift - 1);
    }
    const ap_uint<64> shifted = magnitude >> shift;
    ap_int<64> result = shifted;
    if (negative) {
        result = -result;
    }
    return result;
}

ap_int<64> apply_scale(ap_int<64> value, sr::scale_t multiplier,
                       sr::shift_t shift, ap_uint<2> rounding_mode) {
#pragma HLS INLINE
    const ap_int<64> product = value * multiplier;
    return rounded_shift(product, shift, rounding_mode);
}

sr::activation_t narrow_int8(ap_int<64> value, bool enable_saturation) {
#pragma HLS INLINE
    if (enable_saturation) {
        if (value > 127) {
            return 127;
        }
        if (value < -128) {
            return -128;
        }
    }
    return static_cast<sr::activation_t>(value);
}

}  // namespace

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
    ap_uint<1> enable_saturation) {
#pragma HLS INTERFACE mode=axis port=acc_in
#pragma HLS INTERFACE mode=axis port=activation_out
#pragma HLS INTERFACE mode=ap_memory port=requant_multiplier
#pragma HLS INTERFACE mode=ap_memory port=requant_shift
#pragma HLS INTERFACE mode=ap_memory port=output_zero_point
#pragma HLS INTERFACE mode=ap_memory port=prelu_multiplier
#pragma HLS INTERFACE mode=ap_memory port=prelu_shift
#pragma HLS INTERFACE mode=s_axilite port=spatial_positions bundle=control
#pragma HLS INTERFACE mode=s_axilite port=output_channels bundle=control
#pragma HLS INTERFACE mode=s_axilite port=rounding_mode bundle=control
#pragma HLS INTERFACE mode=s_axilite port=enable_prelu bundle=control
#pragma HLS INTERFACE mode=s_axilite port=prelu_before_requant bundle=control
#pragma HLS INTERFACE mode=s_axilite port=enable_saturation bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control

position_loop:
    for (ap_uint<32> position = 0; position < spatial_positions; ++position) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=230400 avg=230400
    channel_loop:
        for (int channel = 0; channel < output_channels; ++channel) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=16 avg=8
            ap_int<64> value = acc_in.read();

            if (enable_prelu && prelu_before_requant && value < 0) {
                value = apply_scale(value, prelu_multiplier[channel],
                                    prelu_shift[channel], rounding_mode);
            }

            value = apply_scale(value, requant_multiplier[channel],
                                requant_shift[channel], rounding_mode);
            value += output_zero_point[channel];

            if (enable_prelu && !prelu_before_requant && value < 0) {
                value = apply_scale(value, prelu_multiplier[channel],
                                    prelu_shift[channel], rounding_mode);
            }

            activation_out.write(narrow_int8(value, enable_saturation));
        }
    }
}
