<?php
/** Keeps a show's YouTube connection on the channel it publishes to. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_YouTube_Channel_Guard {

	const PIN_META = 'ng_youtube_pinned_channel_id';

	public static function expected( $pinned, $current ) {
		$pinned  = is_string( $pinned ) ? trim( $pinned ) : '';
		$current = is_string( $current ) ? trim( $current ) : '';
		return '' !== $pinned ? $pinned : $current;
	}

	public static function allows( $expected, $actual ) {
		return '' === $expected || ( is_string( $actual ) && $actual === $expected );
	}
}
