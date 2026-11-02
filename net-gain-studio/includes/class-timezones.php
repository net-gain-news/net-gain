<?php
/**
 * Time zones for the schedule fields.
 *
 * A show's script-generation time is a wall-clock time in a named zone (America/New_York), never a fixed UTC offset: a
 * named zone follows daylight and standard time by itself, an offset does not. Only named zones are accepted anywhere
 * here, which also keeps every stored value readable by the Python pipeline's zoneinfo.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Timezones {

	/** True for a named zone ("America/New_York", "UTC"), false for anything else, including WordPress's "UTC-5" offsets. */
	public static function is_valid( $name ) {
		return is_string( $name ) && '' !== $name && in_array( $name, DateTimeZone::listIdentifiers(), true );
	}

	/** Meta/form sanitizer: a valid zone name, or '' meaning "use the WordPress site timezone". */
	public static function sanitize( $raw ) {
		$raw = is_string( $raw ) ? trim( $raw ) : '';
		return self::is_valid( $raw ) ? $raw : '';
	}

	/** The WordPress site timezone (Settings > General) as a named zone; UTC if the site is set to a manual offset. */
	public static function site() {
		$name = wp_timezone_string();
		return self::is_valid( $name ) ? $name : 'UTC';
	}

	/**
	 * The zone chosen for the show's script generation, as stored: the new field, else the zone the show's retired
	 * "Timezone" field held (so an existing show keeps its exact schedule until someone picks a zone), else ''.
	 */
	public static function stored_script_zone( $show_id ) {
		foreach ( array( 'ng_script_timezone', 'ng_recording_timezone' ) as $key ) {
			$value = self::sanitize( get_post_meta( $show_id, $key, true ) );
			if ( '' !== $value ) {
				return $value;
			}
		}
		return '';
	}

	/** The zone the show's script-generation time, recording days and episode dates are read in. Always a valid zone. */
	public static function script_zone( $show_id ) {
		$stored = self::stored_script_zone( $show_id );
		return '' !== $stored ? $stored : self::site();
	}

	/** The zone a scheduled publish time is read in: the show's own choice, else the WordPress site timezone. */
	public static function publish_zone( $show_id ) {
		$stored = self::sanitize( get_post_meta( $show_id, 'ng_publish_timezone', true ) );
		return '' !== $stored ? $stored : self::site();
	}

	/** "4:35 pm EST (UTC-05:00)": the zone's clock right now, so the person choosing sees which side of a shift it is on. */
	public static function now_label( $zone ) {
		$now = new DateTime( 'now', new DateTimeZone( self::is_valid( $zone ) ? $zone : 'UTC' ) );
		return $now->format( 'g:i a T' ) . ' (UTC' . $now->format( 'P' ) . ')';
	}

	/**
	 * <option>/<optgroup> markup for a zone <select>. The first option is the blank "inherit" choice, labelled with the
	 * zone it currently resolves to.
	 */
	public static function select_options( $selected ) {
		$html = sprintf(
			'<option value=""%s>WordPress site timezone (%s)</option>',
			selected( '', $selected, false ),
			esc_html( self::site() )
		);

		$groups = array();
		foreach ( DateTimeZone::listIdentifiers() as $id ) {
			$parts = explode( '/', $id, 2 );
			$groups[ count( $parts ) > 1 ? $parts[0] : 'UTC' ][] = $id;
		}

		foreach ( $groups as $region => $ids ) {
			if ( 'UTC' !== $region ) {
				$html .= '<optgroup label="' . esc_attr( $region ) . '">';
			}
			foreach ( $ids as $id ) {
				$label = false === strpos( $id, '/' ) ? $id : str_replace( '_', ' ', explode( '/', $id, 2 )[1] );
				$html .= sprintf( '<option value="%s"%s>%s</option>', esc_attr( $id ), selected( $id, $selected, false ), esc_html( $label ) );
			}
			if ( 'UTC' !== $region ) {
				$html .= '</optgroup>';
			}
		}

		return $html;
	}
}
