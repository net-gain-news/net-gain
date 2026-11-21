<?php
/**
 * A show's LinkedIn page settings (2026-11-20).
 *
 * The pipeline posts each episode's show notes, with a link to the episode page, to the show's own LinkedIn page (a showcase
 * page or a company page). Which page is a setting on the show; the LinkedIn sign-in is an account-wide secret kept on the
 * server by the pipeline and never stored here.
 *
 * Nothing is posted until "Post to LinkedIn" is switched on. Switching it on stamps `ng_linkedin_since`; only episodes whose
 * website page went live after that moment are posted, so turning it on can never back-fill old episodes.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_LinkedIn_Settings {

	/**
	 * Pure: the numeric page id from what was typed - the bare number, or a LinkedIn page address of the form
	 * linkedin.com/showcase/123456789/ or linkedin.com/company/123456789/. Anything else (including a name-only address such as
	 * /company/acme/, which carries no id) is 0, meaning "not set".
	 */
	public static function sanitize_page_id( $raw ) {
		$raw = is_string( $raw ) || is_int( $raw ) ? trim( (string) $raw ) : '';
		if ( preg_match( '/^\d{3,}$/', $raw ) ) {
			return (int) $raw;
		}
		if ( preg_match( '#linkedin\.com/(?:showcase|company)/(\d{3,})(?:[/?\#]|$)#i', $raw, $match ) ) {
			return (int) $match[1];
		}
		return 0;
	}

	/**
	 * Pure: the show's own hashtags from what was typed (spaces, commas or newlines between them, an optional # before each).
	 * Letters, digits and underscores only - so "K-12" becomes K12 - at most 30 characters each, no repeats in any case, at most 10.
	 *
	 * @return string[]
	 */
	public static function sanitize_hashtags( $raw ) {
		$raw  = is_string( $raw ) ? $raw : '';
		$out  = array();
		$seen = array();
		foreach ( preg_split( '/[\s,]+/', $raw, -1, PREG_SPLIT_NO_EMPTY ) as $word ) {
			$word = substr( preg_replace( '/[^A-Za-z0-9_]/', '', str_replace( "\u{2011}", '', $word ) ), 0, 30 );
			if ( '' === $word || isset( $seen[ strtolower( $word ) ] ) ) {
				continue;
			}
			$seen[ strtolower( $word ) ] = true;
			$out[]                       = $word;
			if ( count( $out ) >= 10 ) {
				break;
			}
		}
		return $out;
	}

	/** Pure: should this episode be posted to LinkedIn? Same rule as the Kit email: on, and live after it was switched on. (A show that is on but has no page set stays eligible, so the pipeline reports the missing page instead of silently skipping it.) */
	public static function episode_is_eligible( array $settings, array $step_status ) {
		return Net_Gain_Kit_Settings::episode_is_eligible( $settings, $step_status );
	}

	/** The show's settings as the tick context hands them to the pipeline. */
	public static function for_show( $show_id ) {
		return array(
			'enabled' => (bool) get_post_meta( $show_id, 'ng_linkedin_enabled', true ),
			'since'   => (string) get_post_meta( $show_id, 'ng_linkedin_since', true ),
			'page_id' => self::sanitize_page_id( (string) get_post_meta( $show_id, 'ng_linkedin_page_id', true ) ),
			// The show's own hashtags, as a list; the pipeline adds topic tags after them (linkedin_post.choose_hashtags).
			'hashtags' => self::sanitize_hashtags( (string) get_post_meta( $show_id, 'ng_linkedin_hashtags', true ) ),
		);
	}
}
