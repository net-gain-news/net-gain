<?php
/**
 * A show's Kit (kit.com) email settings (2026-11-06).
 *
 * The pipeline creates and sends each show's daily episode email, and its weekly roundup, through Kit's API instead of
 * Kit's RSS automations (which cost a paid plan and add a 15 to 46 minute pickup wait plus a fixed 30 minute send delay). Everything
 * that differs between shows lives here, on the show: the audience (a Kit tag), the layout template, the sender, the
 * weekly day, time and zone. The Kit API key is an account-wide secret and stays in the pipeline's environment.
 *
 * Nothing is sent until "Send through Kit" is switched on. Switching it on stamps `ng_kit_since`; only episodes whose website page
 * went live after that moment are emailed, so turning it on can never back-fill old episodes.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Kit_Settings {

	const DAYS = array(
		'mon' => 'Monday',
		'tue' => 'Tuesday',
		'wed' => 'Wednesday',
		'thu' => 'Thursday',
		'fri' => 'Friday',
		'sat' => 'Saturday',
		'sun' => 'Sunday',
	);

	/** Pure: "08:00" for anything that is not a 24-hour HH:MM time. */
	public static function sanitize_time( $raw ) {
		$raw = is_string( $raw ) ? trim( $raw ) : '';
		return preg_match( '/^([01]\d|2[0-3]):[0-5]\d$/', $raw ) ? $raw : '08:00';
	}

	/** Pure: a lower-case day key (mon..sun), or '' (no weekly email). */
	public static function sanitize_day( $raw ) {
		$raw = is_string( $raw ) ? strtolower( trim( $raw ) ) : '';
		return isset( self::DAYS[ $raw ] ) ? $raw : '';
	}

	/** Pure: a Kit id (tag, template) is a positive integer; anything else is 0, meaning "not set". */
	public static function sanitize_id( $raw ) {
		return ( is_numeric( $raw ) && (int) $raw > 0 ) ? (int) $raw : 0;
	}

	/**
	 * Pure: should this episode's daily email be sent through Kit?
	 *
	 * Only when the show has Kit sending on, and the episode's website page went live (the website step's own 'at', a
	 * site-local "Y-m-d H:i:s") at or after the moment sending was switched on. Older episodes were emailed by the RSS
	 * automation (or before there was an email at all) and must never be emailed again.
	 *
	 * @param array $settings    for_show()'s result (needs 'enabled' and 'since').
	 * @param array $step_status The episode's ng_step_status.
	 */
	public static function episode_is_eligible( array $settings, array $step_status ) {
		if ( empty( $settings['enabled'] ) || empty( $settings['since'] ) ) {
			return false;
		}
		$website = $step_status['website_published'] ?? array();
		if ( ! in_array( $website['status'] ?? 'pending', array( 'done', 'degraded' ), true ) || empty( $website['at'] ) ) {
			return false;
		}
		return strcmp( (string) $website['at'], (string) $settings['since'] ) >= 0;
	}

	/** The show's settings as the tick context hands them to the pipeline. Weekly keys are empty/0 when the weekly email is off. */
	public static function for_show( $show_id, $series_slug = '' ) {
		$day_raw = get_post_meta( $show_id, 'ng_kit_weekly_day', true );
		$day     = self::sanitize_day( $day_raw );
		$zone    = Net_Gain_Timezones::sanitize( get_post_meta( $show_id, 'ng_kit_weekly_timezone', true ) );
		$zone    = '' !== $zone ? $zone : Net_Gain_Timezones::site();

		return array(
			'enabled'            => (bool) get_post_meta( $show_id, 'ng_kit_enabled', true ),
			'since'              => (string) get_post_meta( $show_id, 'ng_kit_since', true ),
			'daily_tag_id'       => self::sanitize_id( get_post_meta( $show_id, 'ng_kit_daily_tag_id', true ) ),
			'daily_template_id'  => self::sanitize_id( get_post_meta( $show_id, 'ng_kit_daily_template_id', true ) ),
			'from_email'         => (string) get_post_meta( $show_id, 'ng_kit_from_email', true ),
			'weekly_day'         => $day,
			'weekly_time'        => self::sanitize_time( get_post_meta( $show_id, 'ng_kit_weekly_time', true ) ),
			'weekly_timezone'    => $zone,
			'weekly_tag_id'      => self::sanitize_id( get_post_meta( $show_id, 'ng_kit_weekly_tag_id', true ) ),
			'weekly_template_id' => self::sanitize_id( get_post_meta( $show_id, 'ng_kit_weekly_template_id', true ) ),
			'weekly_last_slot'   => (string) get_post_meta( $show_id, 'ng_kit_weekly_last_slot', true ),
			// The email feed the cards are read from: the site's own address, the show's series.
			'feed_url'           => '' !== $series_slug ? home_url( '/series/' . $series_slug . '/feed/ng-email/' ) : '',
		);
	}
}
